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
    weight: float | None = 30,
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
    # 30×8 → 38kg，32.5×8 → 41.2kg，约 +8%
    assert by_name["上斜哑铃卧推"]["delta_kind"] == "up"
    assert by_name["上斜哑铃卧推"]["delta_label"] == "+8%"
    # 20×12 → 28kg，20×14 → 29.3kg，约 +5%
    assert by_name["绳索夹胸"]["delta_kind"] == "up"
    assert by_name["绳索夹胸"]["delta_label"] == "+5%"


def test_session_compare_uses_epley_not_reps():
    """次数降、重量升，估算 1RM 仍涨，不能判成退步。"""
    today = date(2026, 10, 10)
    prev = _sess(1, today - timedelta(days=4), [_set("卧推", weight=30, reps=12)])
    curr = _sess(2, today, [_set("卧推", weight=35, reps=8)])
    cmp_ = build_session_compare([curr, prev])
    lift = cmp_["lifts"][0]
    assert lift["delta_kind"] == "up"
    assert lift["delta_label"] == "+6%"


def test_session_compare_within_band_is_flat():
    today = date(2026, 10, 10)
    prev = _sess(1, today - timedelta(days=4), [_set("卧推", weight=30, reps=8)])
    curr = _sess(2, today, [_set("卧推", weight=30.5, reps=8)])
    lift = build_session_compare([curr, prev])["lifts"][0]
    assert lift["delta_kind"] == "flat"
    assert lift["delta_label"] == "持平"


def test_bodyweight_reps_drop_is_one_rm_drop():
    today = date(2026, 10, 10)
    prev = _sess(1, today - timedelta(days=3), [_set("俯卧撑", weight=None, reps=15)])
    curr = _sess(2, today, [_set("俯卧撑", weight=None, reps=10)])
    cmp_ = build_session_compare([curr, prev], body_weight=70)
    lift = cmp_["lifts"][0]
    assert lift["delta_kind"] == "down"
    headline = build_headline({"trained_days": 1, "target_days": 4}, [], cmp_, [])
    assert "回落" in headline
    assert "偏沉" not in headline
    assert "俯卧撑" in headline


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
    assert "进步" in headline
    assert "上斜哑铃卧推" in headline
    assert "偏沉" not in headline
    assert lifts[0]["history"] == [28.0, 32.5]


def test_week_volume_compares_with_previous_week():
    today = date(2026, 10, 11)  # Sunday; week starts 10-05
    sessions = [
        _sess(1, date(2026, 10, 1), [_set("卧推", weight=20, reps=10)]),  # 200
        _sess(2, date(2026, 10, 8), [_set("卧推", weight=30, reps=10)]),  # 300
    ]
    week = build_week_rhythm(sessions, target_days=4, today=today)
    assert week["period"] == "week"
    assert week["compare_label"] == "上周"
    assert week["volume_kg"] == 300
    assert week["volume_delta_pct"] == 50
    assert len(week["days"]) == 7


def test_month_rhythm_spans_calendar_month():
    today = date(2026, 10, 11)
    month = build_week_rhythm([], target_days=4, today=today, period="month")
    assert month["period"] == "month"
    assert month["compare_label"] == "上月"
    assert len(month["days"]) == 31
    assert month["days"][0]["date"] == "2026-10-01"
    assert month["volume_delta_pct"] is None
