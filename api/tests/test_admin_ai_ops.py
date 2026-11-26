"""Admin AI Ops：未命中聚合、绑别名热生效、差评导出/忽略。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.auth import issue_admin_token
from app.brain import knowledge
from app.db import get_session
from app.main import app
from app.models import DebugTrace, Exercise, ExerciseAlias, FeedbackEvent


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
    return {"Authorization": f"Bearer {issue_admin_token('admin')}"}


def test_misses_aggregate_and_bind_alias_hot_reload():
    client, engine = _client()
    try:
        knowledge.ensure_index()
        doc = next((d for d in knowledge._docs if d.id and d.name_zh), None)
        assert doc is not None

        with Session(engine) as session:
            session.add(
                Exercise(
                    id=doc.id,
                    name_zh=doc.name_zh,
                    name_en=doc.name_en or "",
                    muscle="胸",
                    gear="器械",
                    modality="抗阻",
                )
            )
            session.add(
                DebugTrace(
                    user_text="蝴蝶机怎么做",
                    payload={
                        "grounding": {
                            "branch": "search",
                            "kb": {
                                "queried": True,
                                "hit": False,
                                "reason": "below_miss",
                                "hits": [],
                                "near_miss": [{"id": doc.id, "name_zh": doc.name_zh, "score": 0.4}],
                            },
                            "search": {"called": True, "query": "蝴蝶机", "results": []},
                        }
                    },
                )
            )
            session.commit()

        headers = _admin_headers()
        listed = client.get("/api/admin/ai-ops/misses?status=pending", headers=headers)
        assert listed.status_code == 200, listed.text
        items = listed.json()["items"]
        assert any(i["display_query"] == "蝴蝶机" or "蝴蝶机" in (i.get("examples") or []) for i in items)
        miss = next(i for i in items if i["norm_query"] == "蝴蝶机" or "蝴蝶" in i["norm_query"])

        # 绑别名前应未命中（或至少不保证命中）
        before = knowledge.ground_question("蝴蝶机")
        assert before.hit is False or before.reason != "alias"

        bound = client.post(
            "/api/admin/ai-ops/misses/bind-alias",
            headers=headers,
            json={
                "norm_query": miss["norm_query"],
                "exercise_id": doc.id,
                "alias": "蝴蝶机",
            },
        )
        assert bound.status_code == 200, bound.text
        body = bound.json()
        assert body["ok"] is True
        assert body["alias"] == "蝴蝶机"

        with Session(engine) as session:
            alias = session.exec(
                select(ExerciseAlias).where(
                    ExerciseAlias.exercise_id == doc.id,
                    ExerciseAlias.alias == "蝴蝶机",
                )
            ).first()
            assert alias is not None
            assert alias.status == "published"

        after = knowledge.ground_question("蝴蝶机")
        assert after.hit is True
        assert after.reason == "alias"

        done = client.get("/api/admin/ai-ops/misses?status=done", headers=headers)
        assert done.status_code == 200
        assert any(i["status"] == "bound" for i in done.json()["items"])
    finally:
        app.dependency_overrides.clear()


def test_feedback_export_and_discard():
    client, engine = _client()
    try:
        with Session(engine) as session:
            session.add(
                FeedbackEvent(
                    rating="down",
                    tags=["bad_answer"],
                    note="答偏了",
                    question="深蹲怎么做",
                    answer="随便",
                    snapshot={
                        "intent": {"topic": "qa"},
                        "route": "chat",
                        "branch": "knowledge",
                        "history": [],
                    },
                    export_status="pending",
                )
            )
            session.commit()
            fid = session.exec(select(FeedbackEvent)).first().id

        headers = _admin_headers()
        listed = client.get("/api/admin/ai-ops/feedbacks?status=pending", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["total"] >= 1

        exported = client.post(
            f"/api/admin/ai-ops/feedbacks/{fid}/export",
            headers=headers,
            json={"write_file": False, "format": "single"},
        )
        assert exported.status_code == 200, exported.text
        assert exported.json()["export_status"] == "exported"
        assert "深蹲怎么做" in exported.json()["yaml"]

        # 再建一条丢弃
        with Session(engine) as session:
            row = FeedbackEvent(
                rating="down",
                tags=["tone"],
                question="你好",
                answer="嗨",
                snapshot={},
                export_status="pending",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            discard_id = row.id

        discarded = client.post(
            f"/api/admin/ai-ops/feedbacks/{discard_id}/discard",
            headers=headers,
        )
        assert discarded.status_code == 200
        assert discarded.json()["export_status"] == "discarded"

        with Session(engine) as session:
            assert session.get(FeedbackEvent, fid).export_status == "exported"
            assert session.get(FeedbackEvent, discard_id).export_status == "discarded"
    finally:
        app.dependency_overrides.clear()


def test_plan_recommend_gaps_and_studio_alias():
    client, engine = _client()
    try:
        knowledge.ensure_index()
        doc = next((d for d in knowledge._docs if d.id and d.name_zh), None)
        assert doc is not None

        with Session(engine) as session:
            session.add(
                Exercise(
                    id=doc.id,
                    name_zh=doc.name_zh,
                    name_en=doc.name_en or "",
                    muscle="腿",
                    gear="自重",
                    modality="抗阻",
                )
            )
            session.add(
                DebugTrace(
                    user_text="有没有产后恢复计划",
                    payload={
                        "intent": {
                            "params": {
                                "plan_kind": "today_session",
                                "recommend_fallback": "recommend_miss",
                                "plan_scene": "女性专项",
                            }
                        },
                        "grounding": {
                            "branch": "recommend_miss",
                            "plan_scene": "女性专项",
                            "recommended_plan_ids": [],
                            "fallback_to_today": True,
                        },
                    },
                )
            )
            session.add(
                DebugTrace(
                    user_text="想要产后训练课表",
                    payload={
                        "intent": {"params": {"plan_kind": "recommend_plan", "plan_scene": "女性专项"}},
                        "grounding": {
                            "branch": "recommend_miss",
                            "plan_scene": "女性专项",
                            "recommended_plan_ids": [],
                        },
                    },
                )
            )
            session.commit()

        headers = _admin_headers()
        gaps = client.get("/api/admin/ai-ops/plan-gaps", headers=headers)
        assert gaps.status_code == 200, gaps.text
        items = gaps.json()["items"]
        assert any(i["label"] == "女性专项" and i["count"] >= 2 for i in items)

        spoken = "工坊口播别名测试词甲"
        added = client.post(
            "/api/admin/ai-ops/aliases",
            headers=headers,
            json={"exercise_id": doc.id, "alias": spoken},
        )
        assert added.status_code == 200, added.text
        assert added.json()["ok"] is True
        assert added.json()["skipped"] is False

        with Session(engine) as session:
            row = session.exec(
                select(ExerciseAlias).where(
                    ExerciseAlias.exercise_id == doc.id,
                    ExerciseAlias.alias == spoken,
                )
            ).first()
            assert row is not None

        hit = knowledge.ground_question(spoken)
        assert hit.hit is True
        assert hit.reason == "alias"
    finally:
        app.dependency_overrides.clear()
