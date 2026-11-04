"""清空业务用户数据（保留动作库）。本地开发用。"""

from __future__ import annotations

from sqlalchemy import text

from app.db import engine

TABLES = [
    "trainingsetlog",
    "trainingsession",
    "exercisestats",
    "chatturn",
    "activechat",
    "authsession",
    "profilehistory",
    "profile",
    "pendingmemory",
    "feedbackevent",
    "debugtrace",
    "myexercise",
]


def main() -> None:
    with engine.begin() as conn:
        for table in TABLES:
            conn.execute(text(f"DELETE FROM {table}"))
        conn.execute(text('DELETE FROM "user"'))
    print("ok: wiped user business data; exercise catalog kept")


if __name__ == "__main__":
    main()
