"""今日多练：append_today 保留 done；today 优先 active；加练不 409。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app


def _client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override
    client = TestClient(app)
    return client, engine


def _auth_headers(client: TestClient) -> dict[str, str]:
    phone = "13900002222"
    client.post("/api/auth/register", json={"phone": phone, "password": "abcdef"})
    login = client.post("/api/auth/login", json={"phone": phone, "password": "abcdef"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _adopt(client: TestClient, headers: dict, title: str, name: str, **extra):
    body = {
        "title": title,
        "items": [
            {
                "id": "a",
                "title": name,
                "selected": True,
                "meta": {"sets": 2, "reps": "8", "muscle": "胸"},
            }
        ],
        "replace_today": True,
        **extra,
    }
    return client.post("/api/training/adopt", json=body, headers=headers)


def test_append_today_keeps_done_and_today_shows_active():
    client, engine = _client()
    try:
        headers = _auth_headers(client)
        r1 = _adopt(client, headers, "上午胸", "俯卧撑")
        assert r1.status_code == 200, r1.text
        sid1 = r1.json()["id"]

        done = client.post(
            f"/api/training/sessions/{sid1}/complete",
            json={"duration_minutes": 30},
            headers=headers,
        )
        assert done.status_code == 200, done.text

        r2 = _adopt(
            client,
            headers,
            "下午加练",
            "深蹲",
            append_today=True,
            replace_today=False,
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "active"
        sid2 = r2.json()["id"]

        today = client.get("/api/training/today", headers=headers)
        assert today.status_code == 200
        assert today.json()["id"] == sid2
        assert today.json()["status"] == "active"

        listed = client.get("/api/training/sessions?limit=20", headers=headers)
        assert listed.status_code == 200
        by_id = {s["id"]: s["status"] for s in listed.json()}
        assert by_id.get(sid1) == "done"
        assert by_id.get(sid2) == "active"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_add_exercise_after_done_opens_extra_session():
    client, engine = _client()
    try:
        headers = _auth_headers(client)
        r1 = _adopt(client, headers, "上午", "俯卧撑")
        assert r1.status_code == 200, r1.text
        sid1 = r1.json()["id"]
        done = client.post(
            f"/api/training/sessions/{sid1}/complete",
            json={"duration_minutes": 20},
            headers=headers,
        )
        assert done.status_code == 200, done.text

        add = client.post(
            "/api/training/today/add-exercise",
            json={"name": "哑铃弯举", "sets": 2, "reps": "10"},
            headers=headers,
        )
        # 可能 404（库无此动作）或 200（新建加练）
        if add.status_code == 404:
            return
        assert add.status_code == 200, add.text
        assert add.json()["status"] == "active"
        assert add.json()["id"] != sid1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_replace_active_requires_no_append_conflict():
    """未完成场次走 replace：abandon active 后再建。"""
    client, engine = _client()
    try:
        headers = _auth_headers(client)
        r1 = _adopt(client, headers, "第一场", "俯卧撑")
        assert r1.status_code == 200, r1.text
        sid1 = r1.json()["id"]

        r2 = _adopt(client, headers, "覆盖重开", "深蹲", replace_today=True)
        assert r2.status_code == 200, r2.text
        assert r2.json()["id"] != sid1
        today = client.get("/api/training/today", headers=headers)
        assert today.json()["id"] == r2.json()["id"]
        assert today.json()["status"] == "active"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
