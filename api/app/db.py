from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings

# Ensure sqlite folder exists
if settings.database_url.startswith("sqlite:///./"):
    db_path = settings.database_url.replace("sqlite:///./", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _promote_text_to_jsonb(conn) -> None:  # type: ignore[no-untyped-def]
    """后补列当初建成了 TEXT。Postgres 的 JSON 类型不会再解析文本，读出来是字符串。"""
    columns = (
        ("chatturn", "card", "NULL"),
        ("chatturn", "suggestions", "'[]'::jsonb"),
    )
    for table, column, empty_sql in columns:
        if not conn.execute(text("SELECT to_regclass(:name)"), {"name": table}).scalar():
            continue
        data_type = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).scalar()
        if data_type != "text":
            continue
        raw_rows = conn.execute(
            text(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL")
        ).fetchall()
        for (raw,) in raw_rows:
            body = str(raw).strip()
            if not body or body == "null":
                continue
            json.loads(body)
        conn.execute(
            text(
                f"ALTER TABLE {table} ALTER COLUMN {column} TYPE jsonb USING ("
                f"CASE WHEN {column} IS NULL OR btrim({column}) = '' OR btrim({column}) = 'null' "
                f"THEN {empty_sql} ELSE {column}::jsonb END)"
            )
        )


def _ensure_columns() -> None:
    """轻量补列：create_all 不会给已有表加新字段。"""
    patches = [
        ("trainingsetlog", "feeling", "VARCHAR"),
        ("exercisestats", "last_feeling", "VARCHAR"),
        ("exercisestats", "last_outcome", "VARCHAR"),
        ("exercisestats", "estimate_1rm", "REAL"),
        ("exercisestats", "best_estimate_1rm", "REAL"),
        ("exercisestats", "recent_1rm_samples", "TEXT"),
        ("trainingsession", "total_volume", "REAL"),
        ("trainingsession", "session_outcome", "VARCHAR"),
        ("trainingsession", "summary", "TEXT"),
        ("trainingsession", "duration_minutes", "INTEGER"),
        ("trainingsession", "duration_source", "VARCHAR"),
        ("trainingsession", "duration_seconds", "INTEGER"),
        ("trainingsession", "timer_started_at", "TIMESTAMP"),
        ("trainingsession", "plan_template_id", "VARCHAR"),
        ("trainingsession", "plan_block_id", "INTEGER"),
        ("trainingsession", "plan_type", "VARCHAR"),
        ("trainingsetlog", "exercise_order", "INTEGER"),
        ("trainingsetlog", "is_warmup", "BOOLEAN"),
        ("profile", "height_cm", "REAL"),
        ("profile", "session_minutes", "INTEGER DEFAULT 45"),
        ("profile", "avoid_exercises", "TEXT"),
        ("profile", "user_id", "INTEGER"),
        ("trainingsession", "user_id", "INTEGER"),
        ("activechat", "user_id", "INTEGER"),
        ("chatturn", "user_id", "INTEGER"),
        ("profilehistory", "user_id", "INTEGER"),
        ("exercisestats", "user_id", "INTEGER"),
        ("chatturn", "conversation_id", "VARCHAR"),
        ("chatturn", "card", "TEXT"),
        ("chatturn", "suggestions", "TEXT"),
        # A0 enriched exercise columns
        ("exercises", "sub_region", "VARCHAR"),
        ("exercises", "movement_pattern", "VARCHAR"),
        ("exercises", "joint_stress", "TEXT"),
        ("exercises", "cues_zh", "TEXT"),
        ("exercises", "common_mistakes_zh", "TEXT"),
        ("exercises", "is_valid_exercise", "BOOLEAN"),
        ("exercises", "needs_review", "BOOLEAN"),
        ("exercises", "updated_at", "TIMESTAMP"),
        # 计划槽位角色（与 roles 肌群列表独立）
        ("exercises", "slot_roles", "TEXT"),
    ]
    url = settings.database_url

    def _patch_type(table: str, column: str, coltype: str) -> str:
        if column == "is_warmup":
            # SQLite 用 0；Postgres 必须用 FALSE，不能写 DEFAULT 0
            return "BOOLEAN DEFAULT 0" if url.startswith("sqlite") else "BOOLEAN DEFAULT FALSE"
        if not url.startswith("sqlite") and (table, column) in {
            ("chatturn", "card"),
            ("chatturn", "suggestions"),
            ("exercises", "joint_stress"),
            ("exercises", "cues_zh"),
            ("exercises", "common_mistakes_zh"),
            ("exercises", "slot_roles"),
        }:
            return "JSONB"
        return coltype

    with engine.begin() as conn:
        if url.startswith("sqlite"):
            for table, column, coltype in patches:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                existing = {r[1] for r in rows}
                if column not in existing and rows:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} ADD COLUMN {column} {_patch_type(table, column, coltype)}"
                        )
                    )
            return
        # Postgres：已有库补列；表还不存在时跳过（create_all 会带上新字段）
        for table, column, coltype in patches:
            exists = conn.execute(
                text("SELECT to_regclass(:name)"),
                {"name": table},
            ).scalar()
            if not exists:
                continue
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {_patch_type(table, column, coltype)}"
                )
            )
        # 身高体重/单次时长可空：引导未选时不写死默认值
        if conn.execute(text("SELECT to_regclass(:name)"), {"name": "profile"}).scalar():
            conn.execute(text("ALTER TABLE profile ALTER COLUMN weight_kg DROP NOT NULL"))
            conn.execute(text("ALTER TABLE profile ALTER COLUMN height_cm DROP NOT NULL"))
            conn.execute(text("ALTER TABLE profile ALTER COLUMN session_minutes DROP NOT NULL"))
        _promote_text_to_jsonb(conn)


def _backfill_slot_roles() -> None:
    """只给空的 slot_roles 预填启发式默认值，不覆盖后台已编辑内容。"""
    from app.models import Exercise
    from app.slot_roles import infer_slot_roles, normalize_slot_roles

    with Session(engine) as session:
        rows = session.exec(select(Exercise)).all()
        changed = 0
        for ex in rows:
            if normalize_slot_roles(ex.slot_roles):
                continue
            inferred = infer_slot_roles(
                movement_pattern=ex.movement_pattern,
                gear=ex.gear,
                modality=ex.modality,
                coach_core=bool(ex.coach_core),
            )
            if not inferred:
                continue
            ex.slot_roles = inferred
            session.add(ex)
            changed += 1
        if changed:
            session.commit()


def init_db() -> None:
    # Register all SQLModel tables on metadata before create_all.
    from app import models as _models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _ensure_columns()
    _backfill_slot_roles()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
