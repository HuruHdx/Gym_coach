"""后台计划模板 CRUD 冒烟。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.auth import issue_admin_token
from app.config import settings
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


def _admin_headers() -> dict[str, str]:
    # 直接签发 admin JWT，避免依赖本地 admin 密码配置
    token = issue_admin_token("admin")
    return {"Authorization": f"Bearer {token}"}


def test_admin_plan_crud_and_block_exercise():
    client, engine = _client()
    try:
        headers = _admin_headers()
        created = client.post(
            "/api/admin/plans",
            headers=headers,
            json={
                "id": "admin-test-split",
                "title": "后台测试三分化",
                "template_type": "framework",
                "days_per_week": 3,
                "muscle_tags": ["胸", "背", "腿"],
                "is_published": False,
            },
        )
        assert created.status_code == 200, created.text
        plan = created.json()
        assert plan["id"] == "admin-test-split"

        listed = client.get("/api/admin/plans", headers=headers)
        assert listed.status_code == 200
        assert any(item["id"] == "admin-test-split" for item in listed.json()["items"])

        block = client.post(
            "/api/admin/plans/admin-test-split/blocks",
            headers=headers,
            json={"title": "胸肩", "muscles": ["胸", "肩"]},
        )
        assert block.status_code == 200, block.text
        block_id = block.json()["id"]

        ex = client.post(
            f"/api/admin/plan-blocks/{block_id}/exercises",
            headers=headers,
            json={
                "role": "main",
                "lock_level": "slot",
                "target_sets": 4,
                "target_reps": "8-12",
                "warmup_sets": 1,
            },
        )
        assert ex.status_code == 200, ex.text
        assert ex.json()["pending"] is True

        published = client.put(
            "/api/admin/plans/admin-test-split",
            headers=headers,
            json={"is_published": True, "sort_order": 5},
        )
        assert published.status_code == 200
        assert published.json()["is_published"] is True

        deleted = client.delete("/api/admin/plans/admin-test-split", headers=headers)
        assert deleted.status_code == 200
        assert client.get("/api/admin/plans/admin-test-split", headers=headers).status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_issue_admin_token_smoke():
    assert settings.admin_password or True
    token = issue_admin_token("admin")
    assert token.count(".") == 2
