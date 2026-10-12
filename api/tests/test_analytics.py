from datetime import date, timedelta

from app.services.analytics_service import (
    SessionSnap,
    SetSnap,
    build_headline,
    build_key_lifts,
    build_muscle_pulse,
    build_session_compare,
    build_week_rhythm,
    primary_muscle,
)


def _set(
    name: str,
    *,
    muscle: str = "胸",
    weight: float = 30,
    reps: int = 8,
    completed: bool = True,
    idx: int = 1,
) -> SetSnap:
    return SetSnap(
        exercise_name=name,
        muscle=muscle,
        set_index=idx,
        actual_weight=weight,
        actual_reps=reps,
        target_weight=weight,
        completed=completed,
    )


def _sess(
    sid: int,
    day: date,
    sets: list[SetSnap],
    *,
    split: str = "胸训",
    status: str = "done",
) -> SessionSnap:
    return SessionSnap(
        id=sid,
        session_date=day,
        split_label=split,
        status=status,
        duration_minutes=45,
        session_outcome="完成",
        sets=sets,
    )


def test_primary_muscle_by_completed_sets():
    s = _sess(
        1,
        date(2026, 10, 9),
        [
            _set("卧推", muscle="胸"),
            _set("飞鸟", muscle="胸"),
            _set("侧平举", muscle="肩"),
        ],
    )
    assert primary_muscle(s) == "胸"


def test_week_rhythm_counts_trained_days():
    today = date(2026, 10, 11)  # Sunday
    sessions = [
        _sess(1, date(2026, 10, 9), [_set("卧推")], split="胸训"),  # Thu
        _sess(2, date(2026, 10, 10), [_set("引体", muscle="背")], split="背训"),  # Fri
    ]
    week = build_week_rhythm(sessions, target_days=4, today=today)
    assert week["trained_days"] == 2
    assert week["target_days"] == 4
    trained = [d for d in week["days"] if d["trained"]]
    assert len(trained) == 2
    assert any(d["is_today"] for d in week["days"])


def test_session_compare_weight_and_reps_delta():
    today = date(2026, 10, 10)
    prev = _sess(
        1,
        today - timedelta(days=5),
        [
            _set("上斜哑铃卧推", weight=30, reps=8),
            _set("绳索夹胸", weight=20, reps=12),
        ],
    )
    curr = _sess(
        2,
        today,
        [
            _set("上斜哑铃卧推", weight=32.5, reps=8),
            _set("绳索夹胸", weight=20, reps=14),
        ],
    )
    cmp_ = build_session_compare([curr, prev])
    assert cmp_ is not None
    assert cmp_["muscle"] == "胸"
    assert cmp_["prev_date"] == prev.session_date.isoformat()
    by_name = {x["exercise_name"]: x for x in cmp_["lifts"]}
    assert by_name["上斜哑铃卧推"]["delta_kind"] == "up"
    assert by_name["上斜哑铃卧推"]["delta_label"] == "+2.5kg"
    assert by_name["绳索夹胸"]["delta_kind"] == "up"
    assert by_name["绳索夹胸"]["delta_label"] == "+2次"


def test_muscle_pulse_marks_overdue_legs():
    today = date(2026, 10, 11)
    sessions = [
        _sess(1, today - timedelta(days=1), [_set("引体", muscle="背")], split="背训"),
        _sess(2, today - timedelta(days=12), [_set("深蹲", muscle="腿")], split="腿训"),
    ]
    pulse = {p["muscle"]: p for p in build_muscle_pulse(sessions, today)}
    assert pulse["背"]["status"] == "fresh"
    assert pulse["腿"]["status"] == "overdue"
    assert pulse["腿"]["days_since"] == 12
    assert pulse["腿"]["count_30d"] == 1


def test_key_lifts_and_headline():
    today = date(2026, 10, 11)
    old = _sess(
        1,
        today - timedelta(days=20),
        [_set("上斜哑铃卧推", weight=28, reps=8)],
    )
    new = _sess(
        2,
        today - timedelta(days=1),
        [_set("上斜哑铃卧推", weight=32.5, reps=8)],
    )
    lifts = build_key_lifts([old, new], stats=[], muscle_by_name={"上斜哑铃卧推": "胸"}, today=today)
    assert lifts
    assert lifts[0]["exercise_name"] == "上斜哑铃卧推"
    assert lifts[0]["delta_kg"] == 4.5

    week = build_week_rhythm([new], 4, today)
    pulse = build_muscle_pulse([old, new], today)
    cmp_ = build_session_compare([new, old])
    headline = build_headline(week, pulse, cmp_, lifts)
    assert "上斜哑铃卧推" in headline or "胸" in headline
