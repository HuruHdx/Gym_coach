from types import SimpleNamespace

from app.performance import judge_performance, parse_target_reps_bounds, pick_manual_feeling


def _set(i, done, target_w, actual_w, target_r="8-10次", actual_r=10, feeling=None):
    return SimpleNamespace(
        set_index=i,
        completed=done,
        target_weight=target_w,
        actual_weight=actual_w,
        target_reps=target_r,
        actual_reps=actual_r,
        feeling=feeling,
    )


def test_parse_target_reps_bounds():
    assert parse_target_reps_bounds("8-10次") == (8, 10)
    assert parse_target_reps_bounds("12") == (12, 12)
    assert parse_target_reps_bounds("AMRAP") == (None, None)
    assert parse_target_reps_bounds(None) == (None, None)


def test_full_sets_same_weight_and_reps_is_met():
    sets = [_set(1, True, 30, 30, "8-10", 10), _set(2, True, 30, 30, "8-10", 9)]
    assert judge_performance(sets) == "达标"
    assert pick_manual_feeling(sets) is None


def test_partial_sets_is_unfinished():
    sets = [_set(1, True, 30, 30), _set(2, False, 30, 30)]
    assert judge_performance(sets) == "没做完"


def test_weight_beats_reps():
    # 计划 80kg×8-10，实际推到 100kg 但只做了 6 次：重量优先，记加重完成
    sets = [_set(1, True, 80, 100, "8-10次", 6), _set(2, True, 80, 100, "8-10次", 6)]
    assert judge_performance(sets) == "加重完成"


def test_weight_drop_before_extra_reps():
    sets = [_set(1, True, 80, 70, "8-10次", 14)]
    assert judge_performance(sets) == "降重完成"


def test_session_outcome_from_exercises():
    from app.performance import judge_session, session_volume

    assert judge_session(["加重完成", "达标"]) == "有突破"
    assert judge_session(["没做完", "次数未达标", "达标"]) == "偏吃力"
    assert judge_session(["没做完", "没做完"]) == "未完成"
    assert session_volume([_set(1, True, 80, 100, "8-10次", 6)]) == 600


def test_reps_drop_triggers_deficit():
    # 目标 8-10次，第2组只做了 5 次（少于8-2=6次，严重力竭未达标）
    sets = [_set(1, True, 30, 30, "8-10次", 9), _set(2, True, 30, 30, "8-10次", 5)]
    assert judge_performance(sets) == "次数未达标"


def test_reps_surplus_triggers_surplus():
    # 目标 10 次，两组都做了 13 次，超出上限 2 次以上
    sets = [_set(1, True, 30, 30, "10次", 13), _set(2, True, 30, 30, "10次", 14)]
    assert judge_performance(sets) == "超额完成"


def test_summary_skips_tonnage_dump():
    from types import SimpleNamespace

    from app.performance import build_session_summary

    row = SimpleNamespace(completed=True, muscle="胸", feeling="力竭", note="有点吃力")
    text = build_session_summary("胸", [("俯卧撑", "没做完", [row])], 40)
    assert "总容量" not in text
    assert "胸部" in text
    assert "俯卧撑" in text
    assert "有点吃力" in text
    assert "40 分钟" in text
    assert "核心" in build_session_summary(
        "胸",
        [("腹肌训练", "达标", [SimpleNamespace(exercise_name="腹肌训练", completed=True, muscle="核心", feeling=None, note=None)])],
        None,
    )
    chosen = build_session_summary(
        "胸",
        [("腹肌训练", "达标", [SimpleNamespace(exercise_name="腹肌训练", completed=True, muscle="全身", feeling=None, note=None)])],
        None,
    )
    assert "全身" in chosen
    assert judge_performance([_set(1, True, 30, 27.5)]) == "降重完成"
    assert judge_performance([_set(1, True, 30, 32.5)]) == "加重完成"


def test_none_completed_skips():
    assert judge_performance([_set(1, False, 30, 30), _set(2, False, 30, 30)]) is None


def test_manual_feeling_wins_and_can_be_absent():
    tagged = [_set(1, True, 30, 30, feeling="轻松"), _set(2, True, 30, 30, feeling="力竭")]
    assert pick_manual_feeling(tagged) == "力竭"
    cleared = [_set(1, True, 30, 30, feeling=None)]
    assert pick_manual_feeling(cleared) is None
