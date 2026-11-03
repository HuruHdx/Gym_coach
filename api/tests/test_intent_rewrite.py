import asyncio

from app.brain.intent_rewrite import (
    apply_coach_routing,
    build_clarification,
    generate_clarification,
    intent_from_model_json,
    merge_intents,
    needs_clarification,
    rewrite_intent,
)
from app.brain.llm import MockLLM
from app.brain.memory import Intent, draft_title_for_intent, format_intent_for_prompt, parse_intent
from app.models import Experience, Goal, Profile


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
        {"agent": "coach_plan", "ready": True, "muscles": ["胸", "腰子", "背"], "fatigue": False},
        "练一下",
    )
    assert intent.muscles == ["胸", "背"]
    assert intent.params.get("agent") == "coach_plan"


def test_structured_muscles_skip_clarification_without_keyword_hit():
    intent = Intent(
        expert="training",
        muscles=["全身"],
        raw="做下有氧",
        params={"source": "llm", "agent": "coach_plan", "ready": True},
    )
    assert not needs_clarification(intent)


def test_knowledge_question_is_chat_not_plan():
    intent = parse_intent("深蹲膝盖怎么避免内扣")
    assert intent.params.get("agent") == "coach_chat"
    assert not needs_clarification(intent)


def test_nutrition_question_is_nutrition_agent():
    intent = parse_intent("晚饭吃什么蛋白高")
    assert intent.params.get("agent") == "nutrition"
    assert intent.expert == "nutrition"


def test_cardio_is_a_named_session_not_a_clarification():
    text = "我今天只想出出汗 做下有氧"
    intent = parse_intent(text)
    assert intent.expert == "training"
    assert intent.params.get("cardio") is True
    assert intent.params.get("modality") == ["有氧"]
    assert intent.muscles == ["全身"]
    assert not needs_clarification(intent)
    assert draft_title_for_intent(intent) == "有氧"
    line = format_intent_for_prompt(intent)
    assert "课型=有氧" in line
    assert "处方=时长与强度" in line
    assert "不要" not in line
    assert "agent=" not in line
    assert "部位=全身" not in line


def test_cut_goal_alone_is_ready_plan():
    intent = parse_intent("想减脂，练一下")
    assert intent.params.get("agent") == "coach_plan"
    assert intent.params.get("goal") == "减脂"
    assert not needs_clarification(intent)


def test_how_to_cut_is_chat_not_plan():
    intent = parse_intent("减脂该怎么练")
    assert intent.params.get("agent") == "coach_chat"


def test_mobility_session_skips_clarification():
    intent = parse_intent("出差久坐，肩颈拉伸放松，15分钟")
    assert intent.params.get("agent") == "coach_plan"
    assert "灵活性" in (intent.params.get("modality") or [])
    assert not needs_clarification(intent)
    assert draft_title_for_intent(intent) in ("拉伸", "肩训", "背训", "肩+背")


def test_vague_travel_asks_confirmation():
    intent = parse_intent("出差酒店随便练")
    assert needs_clarification(intent)
    text, options = build_clarification(intent)
    assert "不确定" in text
    assert any("徒手" in o["prompt"] for o in options)
    # 点选后的完整说法必须能直接排课
    follow = parse_intent(options[0]["prompt"])
    assert not needs_clarification(follow)
    assert follow.muscles or follow.params.get("modality")


def test_named_lifts_from_model_skip_clarification():
    """点名由意图模型给出，不再靠口语热词表。"""
    text = "我想这次主要做深蹲和硬拉两个动作就好了，其他的下次再说或者我自己看"
    intent = intent_from_model_json(
        {
            "agent": "coach_plan",
            "ready": True,
            "muscles": [],
            "focus_exercises": ["深蹲", "硬拉"],
            "exclusive_focus": True,
            "rewrite": "只安排深蹲与硬拉",
        },
        text,
    )
    assert intent.params.get("focus_exercises") == ["深蹲", "硬拉"]
    assert intent.params.get("exclusive_focus") is True
    assert not needs_clarification(intent)
    line = format_intent_for_prompt(intent)
    assert "点名动作=深蹲+硬拉" in line
    assert "只排点名动作" in line


def test_rules_no_longer_hotword_named_lifts():
    """规则解析不再把口语动作名写成 focus。"""
    from app.exercises_catalog import find_exercises_in_text

    assert find_exercises_in_text("今天上斜杠铃卧推") == []
    assert find_exercises_in_text("罗马尼亚硬拉") == []
    intent = parse_intent("我想这次主要做深蹲和硬拉两个动作就好了")
    assert not intent.params.get("focus_exercises")


def test_followup_on_existing_draft_is_not_forced_into_four_directions():
    intent = parse_intent("把计划里其他的去掉，我自己看")
    assert intent.expert == "training"
    assert needs_clarification(intent)
    assert not needs_clarification(intent, has_draft=True)


def test_format_dialogue_for_prompt_includes_card_items():
    from app.brain.memory_context import format_short_term

    block = format_short_term(
        [
            {"role": "user", "text": "今天做有氧"},
            {
                "role": "assistant",
                "text": "排好了",
                "card_title": "有氧",
                "card_items": ["跑步", "划船机"],
            },
        ]
    )
    assert "短期记忆" in block
    assert "今天做有氧" in block
    assert "划船机" in block


def test_missing_equipment_exclude_comes_from_model():
    from app.brain.intent_rewrite import is_draft_revision
    from app.brain.memory import draft_title_for_intent, format_intent_for_prompt

    # 规则层不再做否定排除；由意图模型给出 exclude
    assert not parse_intent("不行健身房没有划船机呢").params.get("exclude_exercises")
    intent = intent_from_model_json(
        {
            "agent": "coach_chat",
            "ready": True,
            "muscles": [],
            "exclude_exercises": ["划船机"],
            "rewrite": "替换不可用的划船机",
        },
        "不行健身房没有划船机呢",
    )
    assert intent.params.get("exclude_exercises") == ["划船机"]
    assert not intent.params.get("focus_exercises")
    assert is_draft_revision(intent.raw, intent.params)
    assert draft_title_for_intent(intent) != "划船机"
    line = format_intent_for_prompt(intent)
    assert "排除动作" in line
    assert "划船" in line


def test_also_missing_equipment_revision_cue_without_rule_exclude():
    """「X也没有」：规则不抽 exclude；改稿靠话术 cue / 模型字段。"""
    from app.brain.intent_rewrite import is_draft_revision

    intent = parse_intent("椭圆机也没有")
    assert not intent.params.get("exclude_exercises")
    assert not intent.params.get("focus_exercises")
    assert is_draft_revision(intent.raw, intent.params)


def test_positive_named_rower_comes_from_model():
    intent = intent_from_model_json(
        {
            "agent": "coach_plan",
            "ready": True,
            "muscles": [],
            "modality": ["有氧"],
            "minutes": 20,
            "focus_exercises": ["划船机"],
            "rewrite": "划船机有氧20分钟",
        },
        "今天做划船机有氧20分钟",
    )
    assert intent.params.get("focus_exercises") == ["划船机"]
    assert not intent.params.get("exclude_exercises")


def test_hybrid_uses_model_named_lifts_not_rules_hotwords():
    class NamedLiftLLM(MockLLM):
        async def complete_json(self, system: str, user: str):
            if "【INTENT_REWRITE】" in system:
                return {
                    "agent": "coach_plan",
                    "ready": True,
                    "muscles": [],
                    "focus_exercises": ["深蹲", "硬拉"],
                    "exclusive_focus": True,
                    "rewrite": "只安排深蹲与硬拉",
                }
            return await super().complete_json(system, user)

    text = "我想这次主要做深蹲和硬拉两个动作就好了"
    intent = asyncio.run(rewrite_intent(text, mode="hybrid", llm=NamedLiftLLM()))
    assert intent.params.get("focus_exercises") == ["深蹲", "硬拉"]
    assert intent.params.get("exclusive_focus") is True
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
    intent = intent_from_model_json(
        {
            "agent": "coach_plan",
            "ready": True,
            "muscles": ["核心"],
            "focus_exercises": ["深蹲", "硬拉"],
            "exclusive_focus": False,
            "rewrite": "深蹲硬拉并加腹肌",
        },
        text,
    )
    assert intent.params.get("focus_exercises") == ["深蹲", "硬拉"]
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
            "agent": "coach_plan",
            "ready": True,
            "muscles": ["背"],
            "split": None,
            "equipment": None,
            "fatigue": False,
            "rewrite": "练背",
        },
        "今天没劲了想练背",
    )
    merged = merge_intents(rules, model)
    assert merged.muscles == ["背"]
    assert merged.params.get("fatigue") is True
    assert merged.params.get("source") == "hybrid"


def test_novice_broad_leg_plans_directly():
    intent = parse_intent("今天练腿")
    profile = Profile(goal=Goal.BULK, experience=Experience.NOVICE, weight_kg=70)
    routed = apply_coach_routing(intent, profile)
    assert routed.params.get("ready") is True
    assert not needs_clarification(routed)


def test_advanced_broad_leg_asks_focus():
    intent = parse_intent("今天练腿")
    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    routed = apply_coach_routing(intent, profile)
    assert needs_clarification(routed)
    assert routed.params.get("tension", {}).get("kind") == "focus"
    text, _options = build_clarification(routed)
    assert text == ""


def test_back_width_followup_plans_instead_of_second_clarify():
    """老炮答完「不够宽」后直接排课，不再追问第二层。"""
    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    history = [
        {"role": "user", "text": "今天要练背了"},
        {"role": "assistant", "text": "今天练背想重点拉宽度、练厚度，还是整体都兼顾？"},
    ]
    follow = parse_intent("感觉背不够宽呢")
    follow.params["agent"] = "coach_plan"
    follow.params["tension"] = {"has_tension": True, "kind": "focus"}
    follow.muscles = ["背"]
    routed = apply_coach_routing(follow, profile, history)
    assert routed.params.get("agent") == "coach_plan"
    assert routed.params.get("ready") is True
    assert not needs_clarification(routed)


def test_gibberish_in_open_plan_thread_stays_on_plan():
    """排课线程里的「111」不能掉进闲聊写文字计划。"""
    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    history = [
        {"role": "user", "text": "今天要练背了"},
        {"role": "assistant", "text": "想重点拉宽度还是厚度？"},
        {"role": "user", "text": "感觉背不够宽呢"},
    ]
    stray = Intent(
        expert="chat",
        muscles=["背"],
        raw="111",
        params={"agent": "coach_chat", "ready": True, "goal": "增肌"},
    )
    routed = apply_coach_routing(stray, profile, history)
    assert routed.params.get("agent") == "coach_plan"
    assert routed.params.get("ready") is True
    assert not needs_clarification(routed)


def test_knowledge_question_stays_chat_inside_plan_thread():
    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    history = [{"role": "user", "text": "今天要练背了"}]
    ask = Intent(
        expert="chat",
        muscles=["背"],
        raw="下拉怎么避免借力",
        params={"agent": "coach_chat", "ready": True},
    )
    routed = apply_coach_routing(ask, profile, history)
    assert routed.params.get("agent") == "coach_chat"


def test_comparison_in_plan_thread_is_pulled_back_to_chat():
    """排完课后问两个动作的区别，即使模型判成排课也要拉回问答。"""
    profile = Profile(goal=Goal.BULK, experience=Experience.NOVICE, weight_kg=70)
    history = [
        {"role": "user", "text": "今天练背"},
        {"role": "assistant", "text": "安排好了", "card_title": "背训", "card_items": ["高位下拉", "坐姿划船"]},
    ]
    ask = Intent(
        expert="training",
        muscles=["背"],
        raw="那高位下拉和划船有啥区别",
        params={"agent": "coach_plan", "ready": True, "modality": ["抗阻"]},
    )
    routed = apply_coach_routing(ask, profile, history)
    assert routed.expert == "chat"
    assert routed.params.get("agent") == "coach_chat"
    assert not routed.params.get("tension")


def test_advanced_leg_with_focus_detail_plans_directly():
    """老炮答完侧重后不应再连环追问。"""
    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    follow = parse_intent("今天练腿，侧重股四头肌增肌训练")
    # 模拟模型仍错误地挂上 tension
    follow.params["tension"] = {"has_tension": True, "kind": "focus", "question": "", "suggestions": []}
    follow.params["ready"] = False
    routed = apply_coach_routing(follow, profile)
    assert not needs_clarification(routed)
    assert routed.params.get("ready") is True
    assert not routed.params.get("tension")
    # 股四头肌是解剖名，不能进点名动作
    assert "股四头肌" not in (routed.params.get("focus_exercises") or [])


def test_advanced_leg_with_squat_and_reps_plans_directly():
    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    follow = parse_intent(
        "今天练腿，侧重股四头肌增肌训练，以大重量低次数（4-6次）力量为主，自由深蹲这类复合动作为主"
    )
    follow.params["tension"] = {"has_tension": True, "kind": "focus"}
    follow.params["ready"] = False
    routed = apply_coach_routing(follow, profile)
    assert not needs_clarification(routed)
    assert routed.params.get("ready") is True
    # 规则不再热词点名；模型未给 focus 时靠强度/侧重 cue 直接排
    assert "股四头肌" not in (routed.params.get("focus_exercises") or [])


def test_bulk_vague_cardio_asks_intensity():
    intent = parse_intent("今天做做有氧")
    profile = Profile(goal=Goal.BULK, experience=Experience.INTERMEDIATE, weight_kg=72)
    routed = apply_coach_routing(intent, profile)
    assert needs_clarification(routed)
    assert routed.params.get("tension", {}).get("kind") == "intensity"
    follow = parse_intent("今天就想高强度有氧暴汗练心肺，拉大强度")
    follow = apply_coach_routing(follow, profile)
    assert not needs_clarification(follow)
    assert follow.params.get("intensity") == "high"


def test_sweat_alone_is_not_cardio():
    intent = parse_intent("今天随便出出汗")
    assert intent.params.get("modality") != ["有氧"]
    assert not intent.params.get("cardio")
    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    routed = apply_coach_routing(intent, profile)
    assert needs_clarification(routed)
    assert routed.params.get("tension", {}).get("kind") == "blank"
    # 路由不写死话术，反问交给模型
    text, _options = build_clarification(routed)
    assert text == ""
    from app.brain.memory import format_profile_for_llm

    brief = format_profile_for_llm(profile)
    asked, options = asyncio.run(generate_clarification(routed, brief))
    assert "出出汗" in asked or "出汗" in asked or "练什么" in asked
    assert "老炮" not in asked
    assert options


def test_confirm_relation_never_becomes_a_new_plan():
    """确认当前卡是草案关系，不看原句里有没有某个词。"""
    intent = intent_from_model_json(
        {
            "agent": "coach_plan",
            "muscles": ["腿"],
            "modality": ["抗阻"],
            "draft_relation": "confirm",
            "rewrite": "确认使用当前计划",
        },
        "随便怎么说，只要关系是确认当前这张",
    )
    assert intent.expert == "chat"
    assert intent.params.get("draft_relation") == "confirm"
    assert intent.params.get("adopt_hint") is True
    assert not needs_clarification(intent)


def test_fresh_relation_still_plans():
    intent = intent_from_model_json(
        {
            "agent": "coach_chat",
            "muscles": [],
            "draft_relation": "fresh",
            "rewrite": "放弃当前计划并重排",
        },
        "这张不要了，再来一版",
    )
    assert intent.expert == "training"
    assert intent.params.get("agent") == "coach_plan"
    assert not intent.params.get("adopt_hint")
    assert "重排一堂新课" in format_intent_for_prompt(intent)


def test_change_plan_asks_without_dropping_the_current_part(monkeypatch):
    """换计划但没说换部位：问一次，不写成不练当前部位。"""

    class AskPlan(MockLLM):
        async def complete_json(self, system: str, user: str):
            if "【INTENT_REWRITE】" in system:
                return {
                    "agent": "coach_plan",
                    "muscles": [],
                    "draft_relation": "fresh",
                    "session_target": "ask",
                    "rewrite": "对当前计划不满意，部位去留未说明",
                }
            return await super().complete_json(system, user)

    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    intent = asyncio.run(
        rewrite_intent(
            "换个计划",
            mode="llm",
            llm=AskPlan(),
            profile=profile,
            draft_title="腿训",
        )
    )
    assert intent.params.get("tension", {}).get("kind") == "session"
    assert intent.params.get("open_target") == "腿"
    assert needs_clarification(intent, has_draft=True)
    line = format_intent_for_prompt(intent)
    assert "不要默认放弃当前部位" in line
    assert "不练腿" not in line

    class SaysQuit(MockLLM):
        async def complete_json(self, system: str, user: str):
            return {
                "text": "行，那今天不练腿了——你想换成推的上肢吗？",
                "suggestions": [
                    {"label": "腿再换一版", "prompt": "部位不变，还是练腿，只换一套动作"},
                    {"label": "换成练背", "prompt": "今天改练背"},
                ],
            }

    monkeypatch.setattr("app.brain.intent_rewrite.get_intent_llm", lambda: SaysQuit())
    text, options = asyncio.run(generate_clarification(intent, ""))
    assert "不练腿" not in text
    assert options[0]["prompt"].startswith("部位不变")


def test_same_part_new_exercises_keeps_the_focus_already_stated():
    """部位不变只换动作：沿用上一张已经写过的侧重，不再追问。"""

    class KeepMoves(MockLLM):
        async def complete_json(self, system: str, user: str):
            if "【INTENT_REWRITE】" in system:
                return {
                    "agent": "coach_plan",
                    "muscles": [],
                    "draft_relation": "fresh",
                    "session_target": "keep",
                    "rewrite": "部位不变，只换一套动作",
                }
            return await super().complete_json(system, user)

    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    memory = "教练：今天腿训按股四头肌与后链均衡排，复合动作为主。"
    intent = asyncio.run(
        rewrite_intent(
            "不 换套方案 动作",
            mode="llm",
            llm=KeepMoves(),
            profile=profile,
            draft_title="腿训",
            context=memory,
        )
    )
    assert intent.muscles == ["腿"]
    assert intent.params.get("has_focus_detail") is True
    assert not intent.params.get("tension")
    assert not needs_clarification(intent, has_draft=True)
    line = format_intent_for_prompt(intent)
    assert "部位保持上一张" in line
    assert "不要再追问" in line


def test_named_new_part_still_switches():
    class SwitchBack(MockLLM):
        async def complete_json(self, system: str, user: str):
            if "【INTENT_REWRITE】" in system:
                return {
                    "agent": "coach_plan",
                    "muscles": ["背"],
                    "modality": ["抗阻"],
                    "draft_relation": "fresh",
                    "session_target": "switch",
                    "rewrite": "换成背部训练",
                }
            return await super().complete_json(system, user)

    profile = Profile(goal=Goal.BULK, experience=Experience.NOVICE, weight_kg=72)
    intent = asyncio.run(
        rewrite_intent(
            "今天改练背",
            mode="llm",
            llm=SwitchBack(),
            profile=profile,
            draft_title="腿训",
        )
    )
    assert intent.muscles == ["背"]
    assert intent.params.get("session_target") == "switch"
    assert intent.params.get("tension", {}).get("kind") != "session"


def test_intent_model_does_not_see_profile_or_decide_tension():
    """意图模型只收对话；反问不由它输出的 ready/tension 决定。"""
    seen: dict[str, str] = {}

    class Spy(MockLLM):
        async def complete_json(self, system: str, user: str):
            seen["system"] = system
            seen["user"] = user
            return await super().complete_json(system, user)

    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    asyncio.run(rewrite_intent("今天练腿", mode="llm", llm=Spy(), profile=profile))
    assert "学员属性" not in seen["system"]
    assert "tension" not in seen["system"]
    assert "has_focus_detail" in seen["system"]
    assert "draft_relation" in seen["system"]
    assert "session_target" in seen["system"]
    assert "训练经验" not in seen["user"]
    assert "长期目标" not in seen["user"]


def test_routing_ignores_model_tension_for_novice_leg_day():
    """新手只说练腿：模型即便标了 focus 张力，路由仍直接排。"""

    class FocusTension(MockLLM):
        async def complete_json(self, system: str, user: str):
            return {
                "agent": "coach_plan",
                "ready": False,
                "muscles": ["腿"],
                "modality": ["抗阻"],
                "has_focus_detail": False,
                "tension": {
                    "has_tension": True,
                    "kind": "focus",
                    "question": None,
                    "suggestions": None,
                },
                "rewrite": "腿部抗阻训练",
            }

    profile = Profile(goal=Goal.BULK, experience=Experience.NOVICE, weight_kg=70)
    intent = asyncio.run(
        rewrite_intent("今天练腿", mode="llm", llm=FocusTension(), profile=profile)
    )
    assert intent.params.get("ready") is True
    assert not intent.params.get("tension")
    assert not needs_clarification(intent)


def test_model_focus_detail_skips_advanced_clarify():
    """老炮用口语说出侧重、热词表对不上时，认模型的 has_focus_detail。"""

    class Detail(MockLLM):
        async def complete_json(self, system: str, user: str):
            return {
                "agent": "coach_plan",
                "muscles": ["腿"],
                "modality": ["抗阻"],
                "has_focus_detail": True,
                "focus_exercises": None,
                "rewrite": "大腿前侧多练",
            }

    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    intent = asyncio.run(
        rewrite_intent("大腿前面那块多练一点", mode="llm", llm=Detail(), profile=profile)
    )
    assert intent.params.get("has_focus_detail") is True
    assert intent.params.get("ready") is True
    assert not needs_clarification(intent)
    assert intent.params.get("tension") is None


def test_named_run_skips_cardio_intensity_ask():
    """点名有氧动作由模型给出后，不再追问强度。"""
    intent = intent_from_model_json(
        {
            "agent": "coach_plan",
            "ready": True,
            "muscles": [],
            "modality": ["有氧"],
            "focus_exercises": ["跑步机"],
            "rewrite": "跑步机慢跑",
        },
        "今天想跑步机慢跑",
    )
    profile = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    routed = apply_coach_routing(intent, profile)
    assert not needs_clarification(routed)


def test_qa_kind_decide_kept_only_on_qa():
    decided = intent_from_model_json(
        {"topic": "qa", "domain": "training", "qa_kind": "decide", "muscles": ["胸", "背"]},
        "明天练胸还是练背好",
    )
    assert decided.params.get("qa_kind") == "decide"

    planned = intent_from_model_json(
        {"topic": "plan", "qa_kind": "decide", "muscles": ["背"]},
        "今天练背",
    )
    assert "qa_kind" not in planned.params

    unknown = intent_from_model_json(
        {"topic": "qa", "qa_kind": "advice"},
        "明天练什么",
    )
    assert "qa_kind" not in unknown.params


def test_topic_qa_sets_chat_agent():
    intent = intent_from_model_json(
        {"agent": "coach_plan", "topic": "qa", "muscles": [], "rewrite": "问上次卧推"},
        "我上次卧推多少",
    )
    assert intent.params.get("topic") == "qa"
    assert intent.params.get("agent") == "coach_chat"
    assert intent.expert == "chat"


def test_topic_plan_sets_plan_agent():
    intent = intent_from_model_json(
        {"agent": "coach_chat", "topic": "plan", "muscles": ["背"]},
        "今天练背",
    )
    assert intent.params.get("topic") == "plan"
    assert intent.params.get("agent") == "coach_plan"
    assert intent.expert == "training"


def test_topic_chitchat_sets_chat_agent():
    intent = intent_from_model_json(
        {"agent": "coach_plan", "topic": "chitchat"},
        "今天心情不好，不想练",
    )
    assert intent.params.get("topic") == "chitchat"
    assert intent.params.get("agent") == "coach_chat"


def test_illegal_topic_is_omitted():
    intent = intent_from_model_json(
        {"agent": "coach_chat", "topic": "memory"},
        "你好",
    )
    assert "topic" not in intent.params


def test_domain_nutrition_kept_and_illegal_domain_dropped():
    kept = intent_from_model_json(
        {"agent": "coach_chat", "topic": "qa", "domain": "nutrition"},
        "蛋白粉和增肌粉哪个好",
    )
    assert kept.params.get("domain") == "nutrition"
    dropped = intent_from_model_json(
        {"agent": "coach_chat", "topic": "qa", "domain": "diet"},
        "蛋白粉",
    )
    assert "domain" not in dropped.params


def test_pick_route_follows_topic():
    from app.brain.graph import _pick_route

    plan = Intent(
        expert="training",
        muscles=["背"],
        raw="今天练背",
        params={"agent": "coach_plan", "topic": "plan", "domain": "training", "ready": True},
    )
    meal = Intent(
        expert="training",
        muscles=[],
        raw="帮我排个减脂餐",
        params={"agent": "coach_plan", "topic": "plan", "domain": "nutrition", "ready": True},
    )
    qa = Intent(
        expert="chat",
        muscles=[],
        raw="深蹲怎么做",
        params={"agent": "coach_chat", "topic": "qa", "domain": "training", "ready": True},
    )
    chat = Intent(
        expert="chat",
        muscles=[],
        raw="你好",
        params={"agent": "coach_chat", "topic": "chitchat", "domain": "general", "ready": True},
    )
    assert _pick_route(plan, has_draft=False) == "plan"
    assert _pick_route(meal, has_draft=False) == "nutrition"
    assert _pick_route(qa, has_draft=False) == "chat"
    assert _pick_route(chat, has_draft=False) == "chat"


def test_confirm_keeps_plan_topic_and_does_not_replan():
    from app.brain.graph import _pick_route

    class Confirm(MockLLM):
        async def complete_json(self, system: str, user: str):
            return {
                "agent": "coach_chat",
                "topic": "plan",
                "domain": "training",
                "draft_relation": "confirm",
                "rewrite": "确认使用当前计划",
            }

    intent = asyncio.run(
        rewrite_intent("就这个吧，今天的计划", mode="llm", llm=Confirm(), draft_title="背训")
    )
    assert intent.params.get("topic") == "plan"
    assert intent.params.get("adopt_hint") is True
    assert intent.params.get("agent") == "coach_chat"
    assert _pick_route(intent, has_draft=True) == "chat"
