"""计划模板列表 / 详情 / 展开。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from app.services.plan_seed import ensure_plan_seeds


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
    with Session(engine) as session:
        ensure_plan_seeds(session)
    client = TestClient(app)
    return client, engine


def _auth_headers(client: TestClient) -> dict[str, str]:
    phone = "13900001111"
    client.post("/api/auth/register", json={"phone": phone, "password": "abcdef"})
    login = client.post("/api/auth/login", json={"phone": phone, "password": "abcdef"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_list_and_detail_and_expand_fixed():
    client, engine = _client()
    try:
        headers = _auth_headers(client)
        listed = client.get("/api/plans", headers=headers)
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] >= 3
        ids = {item["id"] for item in body["items"]}
        assert "three-split-classic" in ids
        assert "five-split-classic" in ids
        assert "fixed-push-strength" in ids

        detail = client.get("/api/plans/fixed-push-strength", headers=headers)
        assert detail.status_code == 200
        plan = detail.json()
        assert plan["template_type"] == "fixed"
        assert plan["blocks"]
        block_id = plan["blocks"][0]["id"]

        expanded = client.post(
            "/api/plans/fixed-push-strength/expand",
            headers=headers,
            json={"block_id": block_id},
        )
        assert expanded.status_code == 200
        card = expanded.json()["card"]
        assert card["card_type"] == "training_draft"
        assert card["meta"]["plan_template_id"] == "fixed-push-strength"
        assert card["meta"]["plan_block_id"] == block_id
        assert any(it["title"] for it in card["items"])
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_expand_framework_fills_slots():
    client, engine = _client()
    try:
        headers = _auth_headers(client)
        detail = client.get("/api/plans/three-split-classic", headers=headers)
        assert detail.status_code == 200
        plan = detail.json()
        block = plan["blocks"][0]
        # 详情预览就应配好动作名，不能甩空「槽位·主项」
        preview_named = [ex for ex in block["exercises"] if ex.get("exercise_name")]
        assert len(preview_named) >= 1
        assert any(ex.get("preview_filled") for ex in block["exercises"])

        expanded = client.post(
            "/api/plans/three-split-classic/expand",
            headers=headers,
            json={"block_id": block["id"]},
        )
        assert expanded.status_code == 200
        items = expanded.json()["card"]["items"]
        assert len(items) >= 3
        # 框架型应尽量填上动作，而不是全空槽
        filled = [it for it in items if it.get("selected") and it.get("title")]
        assert len(filled) >= 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
