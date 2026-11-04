"""评测接口：内存库，不碰业务数据库。意图用假实现，避免调用模型。"""

import asyncio

from app.brain.memory import Intent
from app.routers.brain import eval_qa
from app.schemas import EvalQaRequest


def _intent(text: str, **_kwargs):
    if "今天练" in text and "区别" not in text:
        return Intent(
            expert="training",
            muscles=["背"] if "背" in text else [],
            raw=text,
            params={"agent": "coach_plan", "ready": True, "modality": ["抗阻"], "rewrite": text},
        )
    return Intent(
        expert="chat",
        muscles=[],
        raw=text,
        params={"agent": "coach_chat", "rewrite": text},
    )


def _run(monkeypatch, payload: dict) -> dict:
    async def fake(text: str, **kwargs):
        return _intent(text, **kwargs)

    monkeypatch.setattr("app.brain.graph.rewrite_intent", fake)
    return asyncio.run(eval_qa(EvalQaRequest(**payload), "test"))


def test_eval_exact_hit_does_not_search(monkeypatch):
    class _Fake:
        async def complete_json(self, _system, prompt, **kwargs):
            assert "目标肌" in prompt or "上背" in prompt
            return {"text": "杠杆坐姿划船主要练上背，斜方和菱形肌也会一起干活。"}

    monkeypatch.setattr("app.brain.knowledge_reply.get_llm", lambda: _Fake())
    body = _run(monkeypatch, {"question": "杠杆坐姿划船练哪里"})
    assert body["route"] == "chat"
    assert body["branch"] == "kb"
    assert body["citations"] == ["1350"]
    assert body["kb"]["hit"] is True
    assert body["search"]["called"] is False
    assert body["model_called"] is True
    assert "上背" in body["answer"]
    assert "背阔肌" not in body["answer"]


def test_eval_family_name_is_open_knowledge(monkeypatch):
    class _Fake:
        async def complete_json(self, _system, _prompt, **kwargs):
            return {"text": "坐姿划船主要练背，上背和背阔肌都会参与，握距不同侧重点会变一点。"}

    monkeypatch.setattr("app.brain.knowledge_reply.get_llm", lambda: _Fake())
    body = _run(monkeypatch, {"question": "坐姿划船练哪里"})
    assert body["route"] == "chat"
    assert body["branch"] == "knowledge"
    assert body["search"]["called"] is False
    assert body["model_called"] is True
    assert body["citations"] == []
    assert body["suggestions"] == []
    assert "坐姿划船" in body["answer"]
    assert "杠杆" not in body["answer"]


def test_eval_miss_with_empty_fixture_still_calls_model(monkeypatch):
    class _Fake:
        async def complete_json(self, _system, prompt, **kwargs):
            assert "按教练知识" in prompt or "没有外部摘录" in prompt
            return {"text": "新手练背一周 2 次就够，中间隔开一天恢复。"}

    monkeypatch.setattr("app.brain.knowledge_reply.get_llm", lambda: _Fake())
    body = _run(monkeypatch, {"question": "新手一周练几次背合适", "search_fixture": []})
    assert body["branch"] == "search"
    assert body["kb"]["reason"] == "below_miss"
    assert body["search"]["called"] is True
    assert body["model_called"] is True
    assert body["answer"].startswith("新手练背")
    assert "2" in body["answer"]


def test_eval_intent_mode_skips_the_reply(monkeypatch):
    called = {"n": 0}

    class _Fake:
        async def complete_json(self, _system, _prompt, **kwargs):
            called["n"] += 1
            return {"text": "不应被调用"}

    monkeypatch.setattr("app.brain.knowledge_reply.get_llm", lambda: _Fake())
    body = _run(monkeypatch, {"question": "坐姿划船练哪里", "mode": "intent"})
    assert called["n"] == 0
    assert body["route"] == "chat"
    assert body["intent"]["topic"] is None
    assert body["stats"]["hits"] == []


def test_decide_retries_when_basis_is_empty(monkeypatch):
    async def fake(text: str, **_kwargs):
        return Intent(
            expert="chat",
            muscles=["胸", "背"],
            raw=text,
            params={"agent": "coach_chat", "topic": "qa", "qa_kind": "decide", "rewrite": text},
        )

    calls = {"n": 0}

    class _Fake:
        async def complete_json(self, system, _prompt, **kwargs):
            calls["n"] += 1
            assert "basis" in system
            if calls["n"] == 1:
                return {"basis": [], "text": "都行"}
            return {"basis": ["经验"], "text": "你刚开始练，明天先练胸，动作更好找。"}

    monkeypatch.setattr("app.brain.graph.rewrite_intent", fake)
    monkeypatch.setattr("app.brain.knowledge_reply.get_llm", lambda: _Fake())
    body = asyncio.run(
        eval_qa(EvalQaRequest(question="明天练胸还是练背好", profile={"goal": "增肌", "experience": "新手", "weight_kg": 70, "days_per_week": 4, "injuries": []}), "test")
    )
    assert calls["n"] == 2
    assert body["intent"]["qa_kind"] == "decide"
    assert "先练胸" in body["answer"]
    assert "都行" not in body["answer"]


def test_record_question_uses_stats_fixture(monkeypatch):
    called = {"n": 0}

    class _Fake:
        async def complete_json(self, _system, _prompt, **kwargs):
            called["n"] += 1
            return {"text": "不应编重量"}

    monkeypatch.setattr("app.brain.knowledge_reply.get_llm", lambda: _Fake())
    body = _run(
        monkeypatch,
        {
            "question": "我上次哑铃卧推多少",
            "stats_fixture": [{"name": "哑铃卧推", "last_weight": 32.5, "last_reps": 8, "trend": "→"}],
        },
    )
    assert called["n"] == 0
    assert body["branch"] == "memory"
    assert "32.5" in body["answer"]
    assert "没有" not in body["answer"]
    assert any("卧推" in hit["name"] for hit in body["stats"]["hits"])


def test_record_question_without_fixture_does_not_invent(monkeypatch):
    body = _run(monkeypatch, {"question": "我上次卧推多少"})
    assert body["branch"] == "memory"
    assert "没有" in body["answer"]
    assert "kg" not in body["answer"] and "公斤" not in body["answer"]


def test_eval_plan_does_not_run_the_tool_loop(monkeypatch):
    body = _run(monkeypatch, {"question": "今天练背"})
    assert body["route"] == "plan"
    assert body["branch"] == "plan"
    assert body["kb"]["queried"] is False
    assert body["search"]["called"] is False
    assert body["model_called"] is False
    assert "排课" in body["answer"]
