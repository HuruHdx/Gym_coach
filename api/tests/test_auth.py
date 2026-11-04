from __future__ import annotations

import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.auth import hash_password, issue_access_token, require_auth, verify_password
from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Profile, User


def _client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides.pop(require_auth, None)
    client = TestClient(app)
    return client, engine


def test_password_hash_roundtrip():
    h = hash_password("secret12")
    assert verify_password("secret12", h)
    assert not verify_password("wrong", h)


def test_register_login_jwt_bearer_header():
    client, engine = _client()
    try:
        bad = client.post("/api/auth/register", json={"phone": "123", "password": "abcdef"})
        assert bad.status_code == 400

        reg = client.post(
            "/api/auth/register",
            json={"phone": "13800138000", "password": "abcdef", "display_name": "测"},
        )
        assert reg.status_code == 200, reg.text
        assert reg.json()["phone"] == "13800138000"
        assert "access_token" not in reg.json()

        # 无头 → 401
        assert client.get("/api/auth/me").status_code == 401

        login = client.post(
            "/api/auth/login",
            json={"phone": "13800138000", "password": "abcdef"},
        )
        assert login.status_code == 200
        body = login.json()
        token = body["access_token"]
        assert body["token_type"] == "bearer"
        # 确认为 JWT（三段）
        assert token.count(".") == 2
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["typ"] == "access"
        assert str(payload["sub"]) == str(body["user"]["id"])

        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["display_name"] == "测"

        prof = client.get("/api/profile", headers=headers)
        assert prof.status_code == 200
        assert prof.json() is None

        created = client.post(
            "/api/profile",
            headers=headers,
            json={
                "goal": "增肌",
                "experience": "新手",
                "weight_kg": 70,
                "days_per_week": 4,
                "session_minutes": 45,
                "injuries": [],
                "preferences": ["自由重量"],
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["weight_kg"] == 70

        with Session(engine) as session:
            row = session.exec(select(Profile)).one()
            assert row.user_id == me.json()["id"]

        again = client.get("/api/profile", headers=headers)
        assert again.status_code == 200
        assert again.json()["weight_kg"] == 70

        # 伪造 JWT
        bad_jwt = issue_access_token(me.json()["id"]) + "x"
        assert (
            client.get("/api/profile", headers={"Authorization": f"Bearer {bad_jwt}"}).status_code
            == 401
        )

        wrong = client.post(
            "/api/auth/login",
            json={"phone": "13800138000", "password": "badbad"},
        )
        assert wrong.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_new_user_does_not_claim_orphan_profile():
    """新账号必须自己走 onboarding，不能自动吃掉旧无主画像。"""
    client, engine = _client()
    try:
        with Session(engine) as session:
            session.add(Profile(goal="减脂", experience="进阶", weight_kg=68, days_per_week=3))
            session.commit()

        reg = client.post(
            "/api/auth/register",
            json={"phone": "13900139000", "password": "abcdef"},
        )
        assert reg.status_code == 200

        login = client.post(
            "/api/auth/login",
            json={"phone": "13900139000", "password": "abcdef"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        prof = client.get("/api/profile", headers={"Authorization": f"Bearer {token}"})
        assert prof.status_code == 200
        assert prof.json() is None

        with Session(engine) as session:
            orphan = session.exec(select(Profile).where(Profile.user_id == None)).one()  # noqa: E711
            assert orphan.weight_kg == 68
            assert session.exec(select(User)).one().phone == "13900139000"
    finally:
        app.dependency_overrides.clear()


def test_app_token_still_works_for_verify():
    client, _engine = _client()
    try:
        res = client.get(
            "/api/auth/verify",
            headers={"Authorization": f"Bearer {settings.app_token}"},
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True
        assert res.json()["user_id"] is None
    finally:
        app.dependency_overrides.clear()
