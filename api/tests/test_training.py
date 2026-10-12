from app.brain.validate import validate_and_build_blocks
from app.exercises_catalog import alternatives, is_banned_for_injuries
from app.models import TrainingSetLog
from app.services.session_service import minutes_from_seconds, ordered_sets


def test_exercise_order_beats_alphabetical_name():
    rows = [
        TrainingSetLog(id=1, session_id=1, exercise_name="腿举", set_index=1, exercise_order=2),
        TrainingSetLog(id=2, session_id=1, exercise_name="杠铃深蹲", set_index=1, exercise_order=1),
        TrainingSetLog(id=3, session_id=1, exercise_name="杠铃深蹲", set_index=2, exercise_order=1),
    ]
    assert [row.exercise_name for row in ordered_sets(rows)] == ["杠铃深蹲", "杠铃深蹲", "腿举"]


def test_legacy_sets_keep_insert_order():
    rows = [
        TrainingSetLog(id=10, session_id=1, exercise_name="腿举", set_index=1, exercise_order=0),
        TrainingSetLog(id=11, session_id=1, exercise_name="杠铃深蹲", set_index=1, exercise_order=0),
        TrainingSetLog(id=12, session_id=1, exercise_name="腿举", set_index=2, exercise_order=0),
    ]
    assert [row.exercise_name for row in ordered_sets(rows)] == ["腿举", "腿举", "杠铃深蹲"]


def test_minutes_from_seconds_rounds_for_calories():
    assert minutes_from_seconds(0) is None
    assert minutes_from_seconds(45) == 1
    assert minutes_from_seconds(42 * 60) == 42
    assert minutes_from_seconds(90) == 2


def test_injury_bans_deadlift_for_waist():
    assert is_banned_for_injuries("硬拉", ["腰"])
    assert is_banned_for_injuries("杠铃深蹲", ["膝盖"])
    assert not is_banned_for_injuries("哑铃卧推", ["腰"])


def test_alternatives_excludes_banned():
    opts = alternatives("腿", injuries=["膝盖"])
    assert "深蹲" not in "".join(opts)
    assert "腿举" in opts or "臀桥" in opts


def test_deadlift_shows_up_for_leg_role_swap():
    opts = alternatives("腿")
    assert "杠铃硬拉" in opts
    assert "罗马尼亚硬拉" in opts


def test_validate_drops_banned_items():
    raw = {
        "text": "练腿",
        "card": {
            "card_type": "training_draft",
            "title": "腿训",
            "items": [
                {"id": "1", "title": "硬拉", "meta": {"sets": 3, "reps": "5", "weight": 80, "muscle": "腿"}, "selected": True},
                {"id": "2", "title": "腿举", "meta": {"sets": 4, "reps": "10", "weight": 100, "muscle": "腿"}, "selected": True},
            ],
        },
    }
    blocks = validate_and_build_blocks(raw, injuries=["腰"])
    card = next(b for b in blocks if b.kind == "card")
    titles = [i.title for i in card.items]
    assert "硬拉" not in titles
    assert "腿举" in titles
