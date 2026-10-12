import asyncio

from app.brain.intent_rewrite import (
    build_clarification,
    intent_from_model_json,
    merge_intents,
    needs_clarification,
    rewrite_intent,
)
from app.brain.llm import MockLLM
from app.brain.memory import draft_title_for_intent, format_intent_for_prompt, parse_intent


def test_rewrite_hybrid_matches_rules_under_mock():
    text = "出差酒店随便练练"
    intent = asyncio.run(rewrite_intent(text, mode="hybrid", llm=MockLLM()))
    rules = parse_intent(text)
    assert intent.expert == "training"
    assert intent.params.get("equipment") == ["自重"]
    assert intent.params.get("flexible") is True
    assert intent.params.get("source") == "hybrid"
    assert intent.muscles == rules.muscles


def test_rewrite_rules_mode_no_llm():
    intent = asyncio.run(rewrite_intent("今天练上半身", mode="rules", llm=MockLLM()))
    assert set(intent.muscles) == {"胸", "背", "肩"}
    assert intent.params.get("source") == "rules"


def test_sanitize_rejects_unknown_muscles():
    intent = intent_from_model_json(
        {"expert": "training", "muscles": ["胸", "腰子", "背"], "fatigue": False},
        "练一下",
    )
    assert intent.muscles == ["胸", "背"]


def test_vague_travel_asks_confirmation():
    intent = parse_intent("出差酒店随便练")
    assert needs_clarification(intent)
    text, options = build_clarification(intent)
    assert "不确定" in text
    assert any("徒手" in o["prompt"] for o in options)
    # 点选后的完整说法必须能直接排课
    follow = parse_intent(options[0]["prompt"])
    assert not needs_clarification(follow)
    assert follow.muscles


def test_named_lifts_skip_four_direction_chips():
    text = "我想这次主要做深蹲和硬拉两个动作就好了，其他的下次再说或者我自己看"
    intent = parse_intent(text)
    assert intent.params.get("focus_exercises") == ["杠铃深蹲", "杠铃硬拉"]
    assert intent.muscles == []
    assert intent.params.get("exclusive_focus") is True
    assert not needs_clarification(intent)
    line = format_intent_for_prompt(intent)
    assert "点名动作=杠铃深蹲+杠铃硬拉" in line
    assert "只排点名动作" in line
    assert "可作" in line
    assert "部位=腿+背" not in line


def test_longer_exercise_name_beats_alias():
    from app.exercises_catalog import find_exercises_in_text

    assert find_exercises_in_text("今天上斜杠铃卧推") == ["上斜杠铃卧推"]
    assert find_exercises_in_text("罗马尼亚硬拉") == ["罗马尼亚硬拉"]
    assert find_exercises_in_text("直腿硬拉") == ["罗马尼亚硬拉"]
    assert find_exercises_in_text("半程硬拉") == ["杠铃硬拉"]
    assert find_exercises_in_text("哈克深蹲") == ["哈克深蹲"]
    assert find_exercises_in_text("出差酒店随便练") == []


def test_followup_on_existing_draft_is_not_forced_into_four_directions():
    intent = parse_intent("把计划里其他的去掉，我自己看")
    assert intent.expert == "training"
    assert needs_clarification(intent)
    assert not needs_clarification(intent, has_draft=True)


def test_hybrid_keeps_named_lifts_when_model_misses_them():
    class EmptyMuscleLLM(MockLLM):
        async def complete_json(self, system: str, user: str):
            if "【INTENT_REWRITE】" in system:
                return {"expert": "general", "muscles": [], "rewrite": "不清楚练哪"}
            return await super().complete_json(system, user)

    text = "我想这次主要做深蹲和硬拉两个动作就好了"
    intent = asyncio.run(rewrite_intent(text, mode="hybrid", llm=EmptyMuscleLLM()))
    assert intent.params.get("focus_exercises") == ["杠铃深蹲", "杠铃硬拉"]
    assert intent.params.get("exclusive_focus") is True
    assert intent.muscles == []
    assert not needs_clarification(intent)


def test_mock_plan_keeps_only_named_lifts():
    user = (
        "用户说：我想这次主要做深蹲和硬拉两个动作就好了\n"
        "结构化意图：专家=training；点名动作=杠铃深蹲+杠铃硬拉；范围=只排点名动作，不要再加其他动作\n"
    )
    raw = asyncio.run(MockLLM().complete_json("plan", user))
    titles = [item["title"] for item in raw["card"]["items"]]
    assert titles == ["杠铃深蹲", "杠铃硬拉"]
    by_title = {item["title"]: item["meta"]["muscle"] for item in raw["card"]["items"]}
    assert by_title["杠铃深蹲"] == "腿"
    assert by_title["杠铃硬拉"] == "腿"


def test_deadlift_for_back_picks_back_role():
    user = (
        "用户说：今天练背，用半程硬拉顶厚度\n"
        "结构化意图：专家=training；用户点名部位=背；点名动作=杠铃硬拉；"
        "动作用法=杠铃硬拉可作背/腿/全身。meta.muscle 由你按用户这句话从可作里选\n"
    )
    raw = asyncio.run(MockLLM().complete_json("plan", user))
    hard = next(item for item in raw["card"]["items"] if "硬拉" in item["title"])
    assert hard["meta"]["muscle"] == "背"


def test_named_lifts_plus_abs_do_not_become_legs_and_back():
    text = "我今天只想练两个动作 深蹲和硬拉 你安排下 要练到位，最后还有加点腹肌训练"
    intent = parse_intent(text)
    assert intent.params.get("focus_exercises") == ["杠铃深蹲", "杠铃硬拉"]
    assert not intent.params.get("exclusive_focus")
    assert "核心" in intent.muscles
    title = draft_title_for_intent(intent)
    assert title == "深蹲、硬拉、腹肌"
    line = format_intent_for_prompt(intent)
    assert "标题=深蹲、硬拉、腹肌" in line
    assert "部位=腿+背" not in line


def test_muscle_intent_title_is_short_plan_name():
    intent = parse_intent("今天练背")
    assert draft_title_for_intent(intent) == "背训"


def test_named_muscle_skips_confirmation():
    intent = parse_intent("出差酒店徒手练胸")
    assert not needs_clarification(intent)
    assert "胸" in intent.muscles


def test_merge_prefers_model_muscles_keeps_rules_fatigue():
    rules = parse_intent("今天没劲了")
    model = intent_from_model_json(
        {
            "expert": "training",
            "muscles": ["背"],
            "split": None,
            "equipment": None,
            "fatigue": False,
            "flexible": False,
            "rewrite": "练背",
        },
        "今天没劲了想练背",
    )
    merged = merge_intents(rules, model)
    assert merged.muscles == ["背"]
    assert merged.params.get("fatigue") is True
    assert merged.params.get("source") == "hybrid"
