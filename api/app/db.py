from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

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
        ("trainingsetlog", "exercise_order", "INTEGER"),
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
    ]
    url = settings.database_url
    with engine.begin() as conn:
        if url.startswith("sqlite"):
            for table, column, coltype in patches:
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                existing = {r[1] for r in rows}
                if column not in existing and rows:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
            return
        # Postgres：已有库补列；表还不存在时跳过（create_all 会带上新字段）
        jsonb_columns = {("chatturn", "card"), ("chatturn", "suggestions")}
        for table, column, coltype in patches:
            exists = conn.execute(
                text("SELECT to_regclass(:name)"),
                {"name": table},
            ).scalar()
            if not exists:
                continue
            if (table, column) in jsonb_columns:
                coltype = "JSONB"
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}")
            )
        # 身高体重改为可空：引导页未选时不写死默认值
        if conn.execute(text("SELECT to_regclass(:name)"), {"name": "profile"}).scalar():
            conn.execute(text("ALTER TABLE profile ALTER COLUMN weight_kg DROP NOT NULL"))
            conn.execute(text("ALTER TABLE profile ALTER COLUMN height_cm DROP NOT NULL"))
        _promote_text_to_jsonb(conn)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_columns()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
