from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, col, or_, select

from app.models import ExerciseStats, MyExercise, TrainingSession, TrainingSetLog, utcnow
from app.performance import (
    build_session_summary,
    judge_performance,
    judge_session,
    pick_manual_feeling,
    reference_set,
    session_volume,
)
from app.schemas import AdoptRequest, DraftItemIn, SessionOut, SetOut, SetPatch
from app.taxonomy import canonicalize_exercise


def _sets_for_item(item: DraftItemIn) -> int:
    raw = item.meta.get("sets", 3)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 3
    return max(1, min(n, 12))


def _weight_for_item(item: DraftItemIn) -> float | None:
    w = item.meta.get("weight")
    if w is None:
        return None
    try:
        return float(w)
    except (TypeError, ValueError):
        return None


def _reps_for_item(item: DraftItemIn) -> str | None:
    r = item.meta.get("reps")
    if r is None:
        return None
    return str(r)


def _muscle_for_item(item: DraftItemIn) -> str | None:
    raw = item.meta.get("muscle")
    return str(raw) if raw else None


def set_to_out(row: TrainingSetLog) -> SetOut:
    return SetOut(
        id=row.id or 0,
        session_id=row.session_id,
        exercise_name=row.exercise_name,
        muscle=row.muscle,
        set_index=row.set_index,
        target_reps=row.target_reps,
        target_weight=row.target_weight,
        actual_weight=row.actual_weight,
        actual_reps=row.actual_reps,
        completed=row.completed,
        feeling=row.feeling,
        note=row.note,
    )


def ordered_sets(sets: list[TrainingSetLog]) -> list[TrainingSetLog]:
    """动作按用户排的顺序，组内按组号。旧数据没排过序时，按写入先后，不按动作名字母。"""
    if any((row.exercise_order or 0) != 0 for row in sets):
        return sorted(sets, key=lambda row: (row.exercise_order or 0, row.set_index, row.id or 0))
    first_id: dict[str, int] = {}
    for row in sets:
        current = first_id.get(row.exercise_name)
        row_id = row.id or 0
        if current is None or row_id < current:
            first_id[row.exercise_name] = row_id
    return sorted(sets, key=lambda row: (first_id.get(row.exercise_name, 0), row.set_index, row.id or 0))


def minutes_from_seconds(seconds: int) -> int | None:
    """计时秒数收成分钟，给海报和以后的热量用。不足 1 分钟但确实练过，记 1。"""
    if seconds <= 0:
        return None
    return max(1, int(round(seconds / 60)))


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def _freeze_timer(sess: TrainingSession) -> int:
    elapsed = int(sess.duration_seconds or 0)
    if sess.timer_started_at is not None:
        elapsed += max(0, int((utcnow() - sess.timer_started_at).total_seconds()))
        sess.duration_seconds = elapsed
        sess.timer_started_at = None
    return elapsed


def session_to_out(sess: TrainingSession, sets: list[TrainingSetLog]) -> SessionOut:
    done = sum(1 for s in sets if s.completed)
    return SessionOut(
        id=sess.id or 0,
        session_date=sess.session_date.isoformat(),
        split_label=sess.split_label,
        source=sess.source,
        status=sess.status,
        note=sess.note,
        total_volume=sess.total_volume,
        session_outcome=sess.session_outcome,
        summary=sess.summary,
        duration_seconds=int(sess.duration_seconds or 0),
        timer_started_at=_utc_iso(sess.timer_started_at),
        duration_minutes=sess.duration_minutes,
        sets=[set_to_out(s) for s in ordered_sets(sets)],
        progress={"done": done, "total": len(sets)},
    )


def get_today_active(session: Session, day: date | None = None) -> Optional[SessionOut]:
    day = day or date.today()
    sess = session.exec(
        select(TrainingSession)
        .where(TrainingSession.session_date == day)
        .where(or_(TrainingSession.status == "active", TrainingSession.status == "done"))
        .order_by(col(TrainingSession.id).desc())
    ).first()
    if not sess:
        return None
    sets = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == sess.id)).all())
    return session_to_out(sess, sets)


def abandon_today_active(session: Session, day: date) -> None:
    rows = session.exec(
        select(TrainingSession)
        .where(TrainingSession.session_date == day)
        .where(TrainingSession.status == "active")
    ).all()
    for r in rows:
        r.status = "abandoned"
        session.add(r)


def abandon_today_done(session: Session, day: date) -> None:
    rows = session.exec(
        select(TrainingSession)
        .where(TrainingSession.session_date == day)
        .where(TrainingSession.status == "done")
    ).all()
    for r in rows:
        r.status = "abandoned"
        session.add(r)


def today_has_done(session: Session, day: date | None = None) -> bool:
    day = day or date.today()
    row = session.exec(
        select(TrainingSession)
        .where(TrainingSession.session_date == day)
        .where(TrainingSession.status == "done")
        .limit(1)
    ).first()
    return row is not None


def adopt_draft(session: Session, body: AdoptRequest) -> SessionOut:
    day = date.today()
    selected = [it for it in body.items if it.selected]
    if not selected:
        selected = list(body.items)

    if body.replace_today and today_has_done(session, day) and not body.force_replace_done:
        raise HTTPException(
            status_code=409,
            detail="今日训练已完成。若要覆盖重来，请确认后使用 force_replace_done。",
        )

    if body.replace_today:
        abandon_today_active(session, day)
        if body.force_replace_done:
            abandon_today_done(session, day)

    split = body.split_label
    if not split and "·" in body.title:
        split = body.title.split("·", 1)[-1].strip()

    sess = TrainingSession(
        session_date=day,
        split_label=split,
        source="adopted",
        status="active",
    )
    session.add(sess)
    session.commit()
    session.refresh(sess)

    set_rows: list[TrainingSetLog] = []
    for order, item in enumerate(selected, start=1):
        name = canonicalize_exercise(item.title)
        muscle = _muscle_for_item(item)
        n_sets = _sets_for_item(item)
        weight = _weight_for_item(item)
        reps = _reps_for_item(item)
        # seed MyExercise
        existing = session.exec(select(MyExercise).where(MyExercise.name == name)).first()
        if not existing:
            session.add(MyExercise(name=name, muscle=muscle or "全身"))
        for i in range(1, n_sets + 1):
            row = TrainingSetLog(
                session_id=sess.id or 0,
                exercise_name=name,
                muscle=muscle,
                exercise_order=order,
                set_index=i,
                target_reps=reps,
                target_weight=weight,
                actual_weight=weight,
            )
            session.add(row)
            set_rows.append(row)

    session.commit()
    for r in set_rows:
        session.refresh(r)
    session.refresh(sess)
    return session_to_out(sess, set_rows)


def reorder_exercises(session: Session, session_id: int, names: list[str]) -> SessionOut:
    sess = session.get(TrainingSession, session_id)
    if not sess:
        raise KeyError("session not found")
    rows = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == session_id)).all())
    rank: dict[str, int] = {}
    for index, name in enumerate(names):
        rank[name] = index
        rank[canonicalize_exercise(name)] = index

    def sort_key(row: TrainingSetLog) -> tuple[int, int]:
        if row.exercise_name in rank:
            return (rank[row.exercise_name], row.id or 0)
        return (10_000 + (row.exercise_order or 0), row.id or 0)

    ordered_names: list[str] = []
    for row in sorted(rows, key=sort_key):
        if row.exercise_name not in ordered_names:
            ordered_names.append(row.exercise_name)
    for row in rows:
        row.exercise_order = ordered_names.index(row.exercise_name) + 1
        session.add(row)
    session.commit()
    for row in rows:
        session.refresh(row)
    session.refresh(sess)
    return session_to_out(sess, rows)


def patch_set(session: Session, set_id: int, body: SetPatch) -> SetOut:
    row = session.get(TrainingSetLog, set_id)
    if not row:
        raise KeyError("set not found")
    fields = body.model_fields_set
    if "completed" in fields and body.completed is not None:
        row.completed = body.completed
        if body.completed and row.actual_weight is None and row.target_weight is not None:
            row.actual_weight = row.target_weight
    # 允许显式写成 null（自重）；仅看字段是否出现在请求里
    if "actual_weight" in fields:
        row.actual_weight = body.actual_weight
    if "actual_reps" in fields:
        row.actual_reps = body.actual_reps
    if "feeling" in fields:
        row.feeling = body.feeling
    if "note" in fields:
        row.note = body.note
    if "muscle" in fields:
        row.muscle = body.muscle or None
    if "target_weight" in fields:
        row.target_weight = body.target_weight
        if row.actual_weight is None and body.target_weight is not None:
            row.actual_weight = body.target_weight
    session.add(row)
    session.commit()
    session.refresh(row)
    return set_to_out(row)


def recompute_stats_for_exercise(
    session: Session,
    exercise_name: str,
    session_sets: list[TrainingSetLog] | None = None,
) -> None:
    name = canonicalize_exercise(exercise_name)
    if session_sets is not None:
        outcome = judge_performance(session_sets)
        if outcome is None:
            # 一组都没勾：这次跳过，不改上次重量和表现
            return
        manual = pick_manual_feeling(session_sets)
    else:
        outcome = None
        manual = None

    rows = session.exec(
        select(TrainingSetLog)
        .where(TrainingSetLog.exercise_name == name)
        .where(TrainingSetLog.completed == True)  # noqa: E712
        .order_by(TrainingSetLog.id.desc())
        .limit(20)
    ).all()
    if not rows:
        return
    latest = rows[0]
    weights = [r.actual_weight for r in rows if r.actual_weight is not None]
    best = max(weights) if weights else None
    prev = rows[1].actual_weight if len(rows) > 1 else None
    trend = "→"
    if latest.actual_weight is not None and prev is not None:
        if latest.actual_weight > prev:
            trend = "↑"
        elif latest.actual_weight < prev:
            trend = "↓"

    stats = session.exec(select(ExerciseStats).where(ExerciseStats.exercise_name == name)).first()
    if not stats:
        stats = ExerciseStats(exercise_name=name)
    ref = reference_set(session_sets) if session_sets is not None else None
    if ref is not None and ref.actual_weight is not None:
        stats.last_weight = ref.actual_weight
        stats.last_reps = ref.actual_reps
    else:
        stats.last_weight = latest.actual_weight
        stats.last_reps = latest.actual_reps
    if session_sets is not None:
        stats.last_feeling = manual
        stats.last_outcome = outcome
    else:
        stats.last_feeling = latest.feeling
    stats.best_weight = best
    stats.trend = trend
    stats.updated_at = utcnow()
    session.add(stats)


def set_timer(session: Session, session_id: int, action: str) -> SessionOut:
    sess = session.get(TrainingSession, session_id)
    if not sess:
        raise KeyError("session not found")
    if sess.status == "done":
        raise ValueError("session already done")
    now = utcnow()
    if action == "start":
        if sess.timer_started_at is None:
            sess.timer_started_at = now
    elif action == "pause":
        _freeze_timer(sess)
    else:
        raise ValueError("unknown timer action")
    session.add(sess)
    session.commit()
    session.refresh(sess)
    sets = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == session_id)).all())
    return session_to_out(sess, sets)


def set_recorded_duration(session: Session, session_id: int, duration_minutes: int) -> SessionOut:
    """改这场实际练了多久。完成之后也能改，重新生成总结不会覆盖它。"""
    sess = session.get(TrainingSession, session_id)
    if not sess:
        raise KeyError("session not found")
    sess.duration_minutes = int(duration_minutes)
    sess.duration_seconds = int(duration_minutes) * 60
    sess.duration_source = "manual"
    sess.timer_started_at = None
    session.add(sess)
    session.commit()
    session.refresh(sess)
    sets = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == session_id)).all())
    return session_to_out(sess, sets)


def complete_session(
    session: Session,
    session_id: int,
    duration_minutes: int | None = None,
) -> SessionOut:
    sess = session.get(TrainingSession, session_id)
    if not sess:
        raise KeyError("session not found")
    sets = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == session_id)).all())
    by_name: dict[str, list[TrainingSetLog]] = {}
    for s in sets:
        by_name.setdefault(s.exercise_name, []).append(s)
    outcomes: list[tuple[str, str]] = []
    for name, group in by_name.items():
        outcome = judge_performance(group)
        if outcome is None:
            continue
        outcomes.append((name, outcome))
        recompute_stats_for_exercise(session, name, session_sets=group)
    volume = session_volume(sets)
    session_outcome = judge_session([o for _, o in outcomes])
    already_done = sess.status == "done"
    if not already_done:
        seconds = _freeze_timer(sess)
        if duration_minutes is not None:
            sess.duration_seconds = int(duration_minutes) * 60
            sess.duration_minutes = int(duration_minutes)
            sess.duration_source = "manual"
        else:
            sess.duration_minutes = minutes_from_seconds(seconds)
            sess.duration_source = "timer" if sess.duration_minutes else None
    recorded_minutes = sess.duration_minutes
    groups = [(name, outcome, by_name[name]) for name, outcome in outcomes]
    sess.total_volume = volume
    sess.session_outcome = session_outcome
    sess.summary = build_session_summary(sess.split_label, groups, recorded_minutes)
    sess.status = "done"
    session.add(sess)
    session.commit()
    session.refresh(sess)
    sets = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == session_id)).all())
    return session_to_out(sess, sets)


def list_sessions(session: Session, limit: int = 20) -> list[SessionOut]:
    rows = session.exec(
        select(TrainingSession)
        .where(or_(TrainingSession.status == "active", TrainingSession.status == "done"))
        .order_by(col(TrainingSession.session_date).desc(), col(TrainingSession.id).desc())
        .limit(limit)
    ).all()
    out: list[SessionOut] = []
    for sess in rows:
        sets = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == sess.id)).all())
        out.append(session_to_out(sess, sets))
    return out


def get_session_detail(session: Session, session_id: int) -> SessionOut:
    sess = session.get(TrainingSession, session_id)
    if not sess:
        raise KeyError("session not found")
    sets = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == session_id)).all())
    return session_to_out(sess, sets)


def build_coach_session_context(session: Session, session_id: int) -> str:
    """构建供大模型复盘的深度上下文：包含学员画像、纵向历史对比、今日现场各动作表现、体感与备注。"""
    from app.models import Profile

    sess = session.get(TrainingSession, session_id)
    if not sess:
        return ""
    profile = session.exec(select(Profile).limit(1)).first()
    sets = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == session_id)).all())

    p_info = []
    if profile:
        goal_val = profile.goal.value if hasattr(profile.goal, "value") else str(profile.goal)
        exp_val = profile.experience.value if hasattr(profile.experience, "value") else str(profile.experience)
        p_info.append(f"目标：{goal_val}")
        p_info.append(f"经验：{exp_val}")
        if profile.height_cm:
            p_info.append(f"身高：{profile.height_cm:g}cm")
        if profile.weight_kg:
            p_info.append(f"体重：{profile.weight_kg}kg")
        minutes = getattr(profile, "session_minutes", None) or 45
        p_info.append(f"单次约{minutes}分钟")
        if profile.preferences:
            p_info.append(f"器械：{'/'.join(profile.preferences)}")
        if profile.injuries:
            p_info.append(f"伤痛：{'、'.join(profile.injuries)}")
    profile_line = " | ".join(p_info) if p_info else "无画像信息"

    split = sess.split_label or "训练"
    if sess.duration_source == "timer" and sess.duration_minutes:
        duration = f"{sess.duration_minutes}分钟（计时器记录，可以用来看节奏和组间）"
    elif sess.duration_source == "manual" and sess.duration_minutes:
        duration = (
            f"学员事后补记约{sess.duration_minutes}分钟"
            "（没开计时，不能用来判断练得仓促或组间休息）"
        )
    elif sess.duration_minutes:
        duration = (
            f"记录了{sess.duration_minutes}分钟，但分不清是不是计时器"
            "（不要用它判断节奏或组间）"
        )
    else:
        duration = "未开计时，时长没有参考意义，复盘不要提时长、节奏或组间休息"
    outcome = sess.session_outcome or "完成"

    by_name: dict[str, list[TrainingSetLog]] = {}
    for s in sets:
        by_name.setdefault(s.exercise_name, []).append(s)

    exercise_lines = []
    for name, group in by_name.items():
        done_sets = [s for s in group if s.completed]
        if not done_sets:
            exercise_lines.append(f"- 【{name}】：计划{len(group)}组，全部跳过/未执行。")
            continue

        prev_logs = list(
            session.exec(
                select(TrainingSetLog)
                .where(TrainingSetLog.exercise_name == name)
                .where(TrainingSetLog.session_id != session_id)
                .where(TrainingSetLog.completed == True)  # noqa: E712
                .order_by(col(TrainingSetLog.id).desc())
                .limit(20)
            ).all()
        )

        weights = [s.actual_weight for s in done_sets if s.actual_weight is not None]
        today_max_w = max(weights) if weights else None
        target_w = done_sets[0].target_weight
        target_r = done_sets[0].target_reps

        prev_weights = [s.actual_weight for s in prev_logs if s.actual_weight is not None]
        prev_best_w = max(prev_weights) if prev_weights else None
        prev_last_w = prev_logs[0].actual_weight if prev_logs else None

        perf = judge_performance(group) or "完成"

        desc_parts = [f"完成{len(done_sets)}/{len(group)}组"]
        if target_w is not None:
            desc_parts.append(f"计划{target_w}kg×{target_r or '目标次数'}")
        if today_max_w is not None:
            desc_parts.append(f"今日实际最高{today_max_w}kg")
        elif target_w is None:
            desc_parts.append("自重/轻量")

        if prev_best_w is not None and today_max_w is not None:
            if today_max_w > prev_best_w:
                desc_parts.append(f"【突破历史最好PR】此前最好{prev_best_w}kg，本次+{(today_max_w - prev_best_w):.1f}kg")
            elif today_max_w == prev_best_w:
                desc_parts.append(f"追平历史最好{prev_best_w}kg")
            elif prev_last_w is not None and today_max_w > prev_last_w:
                desc_parts.append(f"比上次({prev_last_w}kg)有所提升")
            elif prev_last_w is not None and today_max_w < prev_last_w:
                desc_parts.append(f"比上次({prev_last_w}kg)降重，负荷未给满")
        elif not prev_logs:
            desc_parts.append("【首次记录该动作】")

        feelings = [s.feeling for s in done_sets if s.feeling]
        if feelings:
            desc_parts.append(f"学员打标体感：{'/'.join(feelings)}")

        notes = [s.note.strip() for s in done_sets if s.note and s.note.strip()]
        if notes:
            desc_parts.append(f"学员备注：{'；'.join(notes)}")

        desc_parts.append(f"单项判定：{perf}")
        exercise_lines.append(f"- 【{name}】：{'，'.join(desc_parts)}")

    return (
        f"【学员画像】{profile_line}\n"
        f"【本场训练】部位：{split} | 记录时长：{duration} | 系统综合状态：{outcome}\n"
        f"【各动作纵向历史对比与现场表现】\n"
        + "\n".join(exercise_lines)
    )
