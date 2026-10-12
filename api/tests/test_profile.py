from app.brain.memory import Intent, apply_profile_defaults, build_profile_summary
from app.models import Experience, Goal, Profile


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
    assert "身高=175cm" in s
    assert "单次约=45分钟" in s
    assert "器械偏好=自由重量、自重" in s
    assert "伤痛=腰" in s


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
