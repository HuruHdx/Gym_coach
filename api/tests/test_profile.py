from sqlmodel import Session, SQLModel, create_engine

from app.brain.memory import (
    Intent,
    apply_profile_defaults,
    assemble_memory,
    build_profile_summary,
    format_intent_for_prompt,
)
from app.models import ExerciseStats, Experience, Goal, Profile


def test_build_profile_summary_includes_new_fields():
    p = Profile(
        goal=Goal.BULK,
        experience=Experience.INTERMEDIATE,
        weight_kg=72,
        height_cm=175,
        days_per_week=4,
        session_minutes=45,
        preferences=["自由重量", "自重"],
        injuries=["腰"],
    )
    s = build_profile_summary(p)
    assert "档案：" in s
    assert "身高：175cm" in s
    assert "单次约：45分钟" in s
    assert "器械偏好：自由重量、自重" in s
    assert "伤痛：腰" in s
    assert "长期目标：增肌" in s
    assert "有训练基础" in s


def test_cardio_profile_summary_demotes_long_term_goal():
    p = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72, session_minutes=45)
    s = build_profile_summary(p, modalities=["有氧"])
    assert "长期目标：增肌" in s
    assert "多年训练" in s
    assert "老炮" not in s


def test_negated_heavy_lifting_is_not_a_strength_goal():
    from app.brain.memory import _extract_goal

    assert _extract_goal("今天不想上重量，给我排个能出汗的有氧计划") is None


def test_sweat_cardio_does_not_rewrite_goal_to_cut():
    p = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72, session_minutes=45)
    intent = Intent(
        expert="training",
        muscles=["全身"],
        raw="今天就想高强度有氧暴汗练心肺，拉大强度",
        params={
            "agent": "coach_plan",
            "ready": True,
            "modality": ["有氧"],
            "cardio": True,
            "goal": "减脂",
            "intensity": "high",
        },
    )
    out = apply_profile_defaults(intent, p)
    assert out.params.get("goal") != "减脂"
    line = format_intent_for_prompt(out, p)
    assert "目标=减脂" not in line
    assert "老炮" not in line


def test_profile_goal_does_not_override_routing_tension():
    p = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    intent = Intent(
        expert="training",
        muscles=["腿"],
        raw="今天练腿",
        params={
            "agent": "coach_plan",
            "ready": False,
            "modality": ["抗阻"],
            "tension": {"has_tension": True, "kind": "focus", "question": "", "suggestions": []},
        },
    )
    out = apply_profile_defaults(intent, p)
    assert out.params.get("goal_source") == "profile"
    assert out.params.get("ready") is False
    assert out.params["tension"]["kind"] == "focus"


def test_apply_profile_defaults_skips_goal_on_pure_cardio():
    p = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72, session_minutes=45)
    intent = Intent(
        expert="training",
        muscles=["全身"],
        raw="出出汗做有氧",
        params={"agent": "coach_plan", "ready": True, "modality": ["有氧"], "cardio": True},
    )
    out = apply_profile_defaults(intent, p)
    assert "goal" not in out.params
    line = format_intent_for_prompt(out)
    assert "目标=" not in line
    assert "课型=有氧" in line


def test_assemble_memory_skips_strength_stats_for_cardio():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        ExerciseStats(
            exercise_name="哑铃卧推",
            last_weight=32.5,
            last_reps=8,
            best_weight=32.5,
            trend="持平",
        )
    )
    session.add(
        ExerciseStats(
            exercise_name="跳绳",
            last_weight=None,
            last_reps=20,
            best_weight=None,
            trend="持平",
        )
    )
    session.commit()
    p = Profile(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72)
    intent = Intent(
        expert="training",
        muscles=["全身"],
        raw="做有氧",
        params={"modality": ["有氧"], "cardio": True},
    )
    pack = assemble_memory(session, intent, p)
    session.close()
    block = pack.as_prompt_block()
    assert "哑铃卧推" not in block
    assert "跳绳" in block
    assert "相关训练：" in block
    assert "长期目标：增肌" in block
    assert "【长期记忆】" in block


def test_assemble_memory_omits_empty_sections_for_cardio():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        ExerciseStats(
            exercise_name="哑铃卧推",
            last_weight=32.5,
            last_reps=8,
            best_weight=32.5,
            trend="→",
        )
    )
    session.commit()
    intent = Intent(
        expert="training",
        muscles=["全身"],
        raw="做有氧",
        params={"modality": ["有氧"], "cardio": True},
    )
    pack = assemble_memory(session, intent, None)
    session.close()
    block = pack.as_prompt_block()
    assert "哑铃卧推" not in block
    assert "相关训练：" not in block
    assert "最近组记录：" not in block
    assert "【长期记忆】" in block
    assert "档案：无" in block


def test_apply_profile_defaults_injects_equipment_and_minutes():
    p = Profile(
        goal=Goal.CUT,
        experience=Experience.NOVICE,
        weight_kg=70,
        session_minutes=30,
        preferences=["自重"],
    )
    intent = Intent(expert="training", muscles=["胸"], params={})
    out = apply_profile_defaults(intent, p)
    assert out.params["equipment"] == ["自重"]
    assert out.params["session_minutes"] == 30


def test_apply_profile_defaults_skips_full_gym_preferences():
    p = Profile(
        preferences=["器械", "自由重量", "绳索", "自重"],
        session_minutes=60,
    )
    intent = Intent(expert="training", muscles=["胸"], params={})
    out = apply_profile_defaults(intent, p)
    assert "equipment" not in out.params
    assert out.params["session_minutes"] == 60


def test_apply_profile_defaults_keeps_user_equipment():
    p = Profile(preferences=["自重"], session_minutes=45)
    intent = Intent(
        expert="training",
        muscles=["胸"],
        params={"equipment": ["自由重量", "自重"]},
    )
    out = apply_profile_defaults(intent, p)
    assert out.params["equipment"] == ["自由重量", "自重"]
