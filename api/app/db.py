from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import event
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


def _ensure_columns() -> None:
    """轻量补列：create_all 不会给已有表加新字段。"""
    from sqlalchemy import text

    patches = [
        ("trainingsetlog", "feeling", "VARCHAR"),
        ("exercisestats", "last_feeling", "VARCHAR"),
        ("exercisestats", "last_outcome", "VARCHAR"),
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
        for table, column, coltype in patches:
            exists = conn.execute(
                text("SELECT to_regclass(:name)"),
                {"name": table},
            ).scalar()
            if not exists:
                continue
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}")
            )


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_columns()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
