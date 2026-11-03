import asyncio

from sqlmodel import Session, SQLModel, create_engine

from app.brain.memory import Intent
from app.brain.pipeline import run_chat_pipeline


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_confirm_relation_does_not_open_a_second_plan(monkeypatch):
    """模型标了 confirm 就不再出卡。原句不必命中某份口头禅名单。"""
    from app.brain.llm import MockLLM

    class ConfirmLLM(MockLLM):
        async def complete_json(self, system: str, user: str):
            if "【INTENT_REWRITE】" in system:
                return {
                    "agent": "coach_plan",
                    "muscles": ["腿"],
                    "modality": ["抗阻"],
                    "draft_relation": "confirm",
                    "rewrite": "确认使用当前计划",
                }
            raise AssertionError("确认当前计划不应进入排课")

    monkeypatch.setattr("app.brain.graph.get_llm", lambda: ConfirmLLM())
    monkeypatch.setattr("app.brain.intent_rewrite.get_llm", lambda: ConfirmLLM())
    session = _session()
    reply = asyncio.run(
        run_chat_pipeline(
            session,
            "就这个吧 今天的计划",
            draft_title="腿+核心",
            draft_items=[
                {"title": "杠铃深蹲", "selected": True, "meta": {"muscle": "腿"}},
                {"title": "悬挂带反向卷腹", "selected": True, "meta": {"muscle": "核心"}},
            ],
        )
    )
    from app.models import DebugTrace
    from sqlmodel import select

    trace = session.exec(select(DebugTrace).order_by(DebugTrace.id.desc())).first()
    session.close()

    nodes = [step["node"] for step in trace.payload["graph"]["steps"]]
    assert nodes == ["rewrite_intent", "ground_knowledge", "chat_reply"]
    assert trace.payload["graph"]["route"] == "chat"
    assert reply.blocks[0].kind == "text"
    assert "采纳" in reply.blocks[0].text
    assert all(block.kind != "card" for block in reply.blocks)


def test_vague_training_stops_at_clarify(monkeypatch):
    async def fake_rewrite(text: str, **_kwargs):
        return Intent(expert="training", muscles=[], raw=text, params={})

    monkeypatch.setattr("app.brain.graph.rewrite_intent", fake_rewrite)
    session = _session()
    reply = asyncio.run(run_chat_pipeline(session, "今天练"))
    from app.models import DebugTrace
    from sqlmodel import select

    trace = session.exec(select(DebugTrace).order_by(DebugTrace.id.desc())).first()
    session.close()

    assert reply.suggestions
    assert reply.blocks[0].kind == "text"
    nodes = [step["node"] for step in trace.payload["graph"]["steps"]]
    assert nodes == ["rewrite_intent", "clarify"]
    assert "draft_plan" not in nodes


def test_named_muscle_runs_plan_nodes(monkeypatch):
    async def fake_rewrite(text: str, **_kwargs):
        return Intent(expert="training", muscles=["胸"], raw=text, params={})

    class FakeLLM:
        async def complete_json(self, system: str, user: str):
            return {
                "text": "胸训",
                "card": {
                    "card_type": "training_draft",
                    "title": "胸训",
                    "items": [
                        {
                            "id": "c1",
                            "title": "哑铃卧推",
                            "selected": True,
                            "meta": {"sets": 3, "reps": "8", "weight": 20, "muscle": "胸"},
                        }
                    ],
                },
            }

    monkeypatch.setattr("app.brain.graph.rewrite_intent", fake_rewrite)
    monkeypatch.setattr("app.brain.graph.get_llm", lambda: FakeLLM())

    session = _session()
    reply = asyncio.run(run_chat_pipeline(session, "今天练胸"))
    from app.models import DebugTrace
    from sqlmodel import select

    trace = session.exec(select(DebugTrace).order_by(DebugTrace.id.desc())).first()
    session.close()

    nodes = [step["node"] for step in (trace.payload.get("graph") or {}).get("steps") or []]
    assert nodes == ["rewrite_intent", "assemble_memory", "draft_plan", "validate"]
    assert reply.blocks
    assert trace.payload["graph"]["route"] == "plan"


def test_dialogue_history_reaches_intent_and_plan_prompt(monkeypatch):
    """近轮对话必须进意图改写与排课 user prompt，而不是只看本句。"""
    seen: dict[str, str] = {}

    async def fake_rewrite(text: str, **kwargs):
        seen["rewrite_history"] = str(kwargs.get("history") or [])
        return Intent(expert="training", muscles=["胸"], raw=text, params={"modality": ["抗阻"]})

    class FakeLLM:
        async def complete_json(self, system: str, user: str):
            seen["plan_user"] = user
            return {
                "text": "胸训",
                "card": {
                    "card_type": "training_draft",
                    "title": "胸训",
                    "items": [
                        {
                            "id": "c1",
                            "title": "哑铃卧推",
                            "selected": True,
                            "meta": {"sets": 3, "reps": "8", "weight": 20, "muscle": "胸"},
                        }
                    ],
                },
            }

    monkeypatch.setattr("app.brain.graph.rewrite_intent", fake_rewrite)
    monkeypatch.setattr("app.brain.graph.get_llm", lambda: FakeLLM())

    history = [
        {"role": "user", "text": "今天练胸"},
        {
            "role": "assistant",
            "text": "安排好了",
            "card_title": "胸训",
            "card_items": ["哑铃卧推", "器械夹胸"],
        },
    ]
    session = _session()
    asyncio.run(
        run_chat_pipeline(
            session,
            "强度低一点",
            history=history,
            draft_title="胸训",
            draft_items=[
                {
                    "id": "c1",
                    "title": "哑铃卧推",
                    "selected": True,
                    "meta": {"sets": 3, "reps": "8", "weight": 20, "muscle": "胸"},
                }
            ],
        )
    )
    session.close()
    assert "今天练胸" in seen["rewrite_history"] or "胸训" in seen["rewrite_history"]
    assert "短期记忆" in seen["plan_user"]
    assert "今天练胸" in seen["plan_user"]
    assert "当前输入" in seen["plan_user"]


def test_missing_rower_revises_draft_keeps_other_moves(monkeypatch):
    """有草稿时说没有划船机 → 改稿替换，不整卡重排成「划船机」空卡。"""

    async def fake_rewrite(text: str, **_kwargs):
        return Intent(
            expert="chat",
            muscles=[],
            raw=text,
            params={"agent": "coach_chat", "ready": True, "exclude_exercises": ["划船机"]},
        )

    class FakeLLM:
        async def complete_json(self, system: str, user: str):
            assert "划船机" in user
            assert "短期记忆" in user
            assert "当前屏幕上的草稿" not in user
            assert "跑步" in user and "动感单车" in user
            return {
                "text": "没有划船机的话，把它换成椭圆机，其余不动。",
                "card": {
                    "card_type": "training_draft",
                    "title": "有氧",
                    "items": [
                        {
                            "id": "c1",
                            "title": "跑步",
                            "selected": True,
                            "meta": {"sets": 1, "reps": "20分钟", "muscle": "全身"},
                        },
                        {
                            "id": "c2",
                            "title": "椭圆机",
                            "selected": True,
                            "meta": {"sets": 1, "reps": "15分钟", "muscle": "全身"},
                        },
                        {
                            "id": "c3",
                            "title": "动感单车",
                            "selected": True,
                            "meta": {"sets": 1, "reps": "10分钟", "muscle": "全身"},
                        },
                    ],
                },
            }

    monkeypatch.setattr("app.brain.graph.rewrite_intent", fake_rewrite)
    monkeypatch.setattr("app.brain.graph.get_llm", lambda: FakeLLM())

    draft_items = [
        {
            "id": "c1",
            "title": "跑步",
            "selected": True,
            "meta": {"sets": 1, "reps": "20分钟", "muscle": "全身"},
        },
        {
            "id": "c2",
            "title": "划船机",
            "selected": True,
            "meta": {"sets": 1, "reps": "15分钟", "muscle": "全身"},
        },
        {
            "id": "c3",
            "title": "动感单车",
            "selected": True,
            "meta": {"sets": 1, "reps": "10分钟", "muscle": "全身"},
        },
    ]
    session = _session()
    reply = asyncio.run(
        run_chat_pipeline(
            session,
            "不行健身房没有划船机呢",
            draft_items=draft_items,
            draft_title="有氧",
        )
    )
    from app.models import DebugTrace
    from sqlmodel import select

    trace = session.exec(select(DebugTrace).order_by(DebugTrace.id.desc())).first()
    session.close()

    assert trace.payload["graph"]["route"] == "plan"
    cards = [b for b in reply.blocks if b.kind == "card"]
    assert cards
    card = cards[0]
    assert card.title == "有氧"
    titles = [it.title for it in card.items]
    assert "划船机" not in titles
    assert "跑步" in titles and "动感单车" in titles
    assert len(card.items) >= 2
