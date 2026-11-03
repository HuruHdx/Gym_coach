"""Related-stats filtering + plan tool loop (mock)."""

import asyncio

from sqlmodel import Session, SQLModel, create_engine, select

from app.brain.llm import MockLLM
from app.brain.memory import Intent, assemble_memory
from app.brain.plan_loop import draft_plan_with_tools
from app.brain.tools import build_tool_context, execute_tool
from app.models import ExerciseStats, Goal, Profile


def _db() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(Profile(goal=Goal.BULK, weight_kg=72, injuries=[]))
    session.add(ExerciseStats(exercise_name="哑铃卧推", last_weight=32.5, best_weight=35, trend="→"))
    session.add(ExerciseStats(exercise_name="杠铃卧推", last_weight=70, best_weight=75, trend="→"))
    session.add(ExerciseStats(exercise_name="杠铃俯身划船", last_weight=50, best_weight=55, trend="↑"))
    session.add(ExerciseStats(exercise_name="绳索杠高位下拉", last_weight=45, best_weight=50, trend="→"))
    session.add(ExerciseStats(exercise_name="滑车45度腿举", last_weight=80, best_weight=90, trend="→"))
    session.commit()
    return session


def test_default_assemble_memory_is_profile_only():
    session = _db()
    profile = session.exec(select(Profile).limit(1)).first()
    intent = Intent(expert="training", muscles=["背"], raw="今天练背", params={"modality": ["抗阻"]})
    pack = assemble_memory(session, intent, profile)
    session.close()
    text = pack.as_prompt_block()
    assert "哑铃卧推" not in text
    assert "腿举" not in text
    assert "候选动作库" not in text


def test_collect_training_stats_names_the_row_and_filters_muscle():
    from app.brain.knowledge_reply import collect_training_stats

    session = _db()
    intent = Intent(
        expert="chat",
        muscles=["胸"],
        raw="我上次杠铃卧推多少",
        params={"topic": "qa", "agent": "coach_chat", "focus_exercises": ["杠铃卧推"]},
    )
    text, stats = collect_training_stats(session, intent, "我上次杠铃卧推多少")
    session.close()
    assert any(hit["name"] == "杠铃卧推" and hit["last_weight"] == 70 for hit in stats["hits"])
    assert all(hit["name"] != "滑车45度腿举" for hit in stats["hits"])
    assert "杠铃卧推" in text
    assert stats["queried"] is True
    assert stats["filter"]["names"] == ["杠铃卧推"]


def test_related_stats_tool_filters_to_back():
    session = _db()
    profile = session.exec(select(Profile).limit(1)).first()
    intent = Intent(expert="training", muscles=["背"], raw="今天练背", params={"modality": ["抗阻"]})
    ctx = build_tool_context(session, intent, profile)
    result = execute_tool("get_related_stats", {"muscles": ["背"], "limit": 10}, ctx)
    session.close()
    joined = "\n".join(result["lines"])
    assert "划船" in joined or "下拉" in joined
    assert "卧推" not in joined
    assert "滑车45度腿举" not in joined


def test_prefetch_assemble_also_filters_by_muscle():
    session = _db()
    profile = session.exec(select(Profile).limit(1)).first()
    intent = Intent(expert="training", muscles=["背"], raw="今天练背", params={"modality": ["抗阻"]})
    pack = assemble_memory(session, intent, profile, prefetch=True)
    session.close()
    text = pack.as_prompt_block()
    assert "卧推" not in text
    assert "腿举" not in text


def test_mock_plan_tool_loop_calls_retrieve_and_submit():
    session = _db()
    profile = session.exec(select(Profile).limit(1)).first()
    intent = Intent(
        expert="training",
        muscles=["背"],
        raw="今天练背",
        params={"modality": ["抗阻"], "agent": "coach_plan", "ready": True},
    )
    ctx = build_tool_context(session, intent, profile)
    user = "用户说：今天练背\n结构化意图：专家=training；部位=背；课型=抗阻\n【长期记忆】\n档案：增肌"
    raw, trace = asyncio.run(draft_plan_with_tools(MockLLM(), user, ctx))
    session.close()
    names = [t["tool"] for t in trace]
    assert "retrieve_exercises" in names
    assert "get_related_stats" in names
    assert "submit_training_draft" in names
    assert raw.get("card", {}).get("items")
