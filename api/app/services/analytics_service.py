"""Deterministic training dashboard analytics — no LLM.

Focus for veterans:
- week rhythm (did you show up)
- muscle recency / 30d frequency (balance)
- same-muscle session-to-session top-set deltas (quality)
- key lift progressive overload (which moves are climbing)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from sqlmodel import Session, col, select

from app.models import ExerciseStats, MyExercise, Profile, TrainingSession, TrainingSetLog

MUSCLES = ("胸", "背", "肩", "腿", "臂", "核心")
WEEKDAY_LABELS = ("一", "二", "三", "四", "五", "六", "日")


@dataclass
class SetSnap:
    exercise_name: str
    muscle: Optional[str]
    set_index: int
    actual_weight: Optional[float]
    actual_reps: Optional[int]
    target_weight: Optional[float]
    completed: bool


@dataclass
class SessionSnap:
    id: int
    session_date: date
    split_label: Optional[str]
    status: str
    duration_minutes: Optional[int]
    session_outcome: Optional[str]
    sets: list[SetSnap]


def _effective_weight(s: SetSnap) -> Optional[float]:
    if s.actual_weight is not None:
        return float(s.actual_weight)
    if s.target_weight is not None:
        return float(s.target_weight)
    return None


def _top_set(sets: list[SetSnap]) -> Optional[SetSnap]:
    """Best completed working set: heaviest, then most reps."""
    done = [s for s in sets if s.completed]
    if not done:
        return None

    def key(s: SetSnap) -> tuple[float, int, int]:
        w = _effective_weight(s)
        return (w if w is not None else -1.0, s.actual_reps or 0, s.set_index)

    return max(done, key=key)


def muscles_from_session(sess: SessionSnap) -> list[str]:
    out: list[str] = []
    for s in sess.sets:
        m = (s.muscle or "").strip()
        if m and m != "全身" and m not in out:
            out.append(m)
    if not out and sess.split_label:
        label = sess.split_label.replace("训", "")
        for m in MUSCLES:
            if m in label and m not in out:
                out.append(m)
    return out


def primary_muscle(sess: SessionSnap) -> Optional[str]:
    """Dominant muscle by completed set count; fallback to split label."""
    counts: dict[str, int] = {}
    for s in sess.sets:
        if not s.completed:
            continue
        m = (s.muscle or "").strip()
        if not m or m == "全身":
            continue
        counts[m] = counts.get(m, 0) + 1
    if counts:
        return max(counts.items(), key=lambda kv: kv[1])[0]
    ms = muscles_from_session(sess)
    return ms[0] if ms else None


def start_of_week_monday(today: date) -> date:
    # Monday=0 … Sunday=6
    return today - timedelta(days=today.weekday())


def build_week_rhythm(
    sessions: list[SessionSnap],
    target_days: int,
    today: date,
) -> dict[str, Any]:
    start = start_of_week_monday(today)
    by_date: dict[date, list[SessionSnap]] = {}
    for s in sessions:
        if s.status not in ("done", "active"):
            continue
        by_date.setdefault(s.session_date, []).append(s)

    days: list[dict[str, Any]] = []
    trained_days = 0
    session_count = 0
    for i in range(7):
        d = start + timedelta(days=i)
        day_sessions = by_date.get(d, [])
        muscles = sorted({m for ss in day_sessions for m in muscles_from_session(ss)})
        trained = len(day_sessions) > 0
        if trained:
            trained_days += 1
            session_count += len(day_sessions)
        primary = day_sessions[0] if day_sessions else None
        mins = None
        if primary and primary.duration_minutes is not None:
            mins = primary.duration_minutes
        done_sets = sum(1 for ss in day_sessions for x in ss.sets if x.completed)
        total_sets = sum(len(ss.sets) for ss in day_sessions)
        pct = round(100 * done_sets / total_sets) if total_sets else None
        days.append(
            {
                "date": d.isoformat(),
                "label": WEEKDAY_LABELS[i],
                "is_today": d == today,
                "trained": trained,
                "muscles": muscles,
                "session_id": primary.id if primary else None,
                "split": primary.split_label if primary else None,
                "duration_minutes": mins,
                "completion_pct": pct,
            }
        )

    return {
        "days": days,
        "trained_days": trained_days,
        "target_days": min(7, max(1, target_days or 4)),
        "sessions": session_count,
    }


def build_muscle_pulse(
    sessions: list[SessionSnap],
    today: date,
    window_days: int = 30,
) -> list[dict[str, Any]]:
    cutoff = today - timedelta(days=window_days - 1)
    done = [s for s in sessions if s.status == "done" and s.session_date >= cutoff]
    # also keep older for "days since" if last train is outside window? No — scan all done
    all_done = [s for s in sessions if s.status == "done"]

    rows: list[dict[str, Any]] = []
    for muscle in MUSCLES:
        dated = [s for s in all_done if muscle in muscles_from_session(s)]
        dated.sort(key=lambda s: (s.session_date, s.id), reverse=True)
        count_30 = sum(1 for s in done if muscle in muscles_from_session(s))
        last = dated[0] if dated else None
        days_since: Optional[int] = None
        if last:
            days_since = (today - last.session_date).days

        # trend from last two sessions of this muscle
        trend = "→"
        if len(dated) >= 2:
            up, down = _session_delta_score(dated[0], dated[1], muscle)
            if up > down:
                trend = "↑"
            elif down > up:
                trend = "↓"

        if days_since is None:
            status = "idle"
        elif days_since >= 10:
            status = "overdue"
        elif days_since <= 1:
            status = "fresh"
        else:
            status = "ok"

        rows.append(
            {
                "muscle": muscle,
                "days_since": days_since,
                "count_30d": count_30,
                "last_date": last.session_date.isoformat() if last else None,
                "last_session_id": last.id if last else None,
                "trend": trend,
                "status": status,
            }
        )

    # overdue / trained first, idle last
    order = {"overdue": 0, "ok": 1, "fresh": 2, "idle": 3}
    rows.sort(key=lambda r: (order.get(r["status"], 9), -(r["count_30d"] or 0)))
    return rows


def _session_delta_score(
    curr: SessionSnap,
    prev: SessionSnap,
    muscle: Optional[str] = None,
) -> tuple[int, int]:
    curr_tops = _tops_by_exercise(curr, muscle)
    prev_tops = _tops_by_exercise(prev, muscle)
    up = down = 0
    for name, c in curr_tops.items():
        p = prev_tops.get(name)
        if not p:
            continue
        cw, cr = _effective_weight(c), c.actual_reps or 0
        pw, pr = _effective_weight(p), p.actual_reps or 0
        if cw is not None and pw is not None:
            if cw > pw + 0.01:
                up += 1
            elif cw < pw - 0.01:
                down += 1
            elif cr > pr:
                up += 1
            elif cr < pr:
                down += 1
        elif cr > pr:
            up += 1
        elif cr < pr:
            down += 1
    return up, down


def _tops_by_exercise(
    sess: SessionSnap,
    muscle: Optional[str] = None,
) -> dict[str, SetSnap]:
    by_name: dict[str, list[SetSnap]] = {}
    for s in sess.sets:
        if muscle:
            m = (s.muscle or "").strip()
            # include if tagged that muscle, or untagged in a mono-muscle session
            if m and m != muscle:
                continue
        by_name.setdefault(s.exercise_name, []).append(s)
    out: dict[str, SetSnap] = {}
    for name, rows in by_name.items():
        top = _top_set(rows)
        if top:
            out[name] = top
    return out


def build_session_compare(
    sessions: list[SessionSnap],
) -> Optional[dict[str, Any]]:
    done = sorted(
        [s for s in sessions if s.status == "done"],
        key=lambda s: (s.session_date, s.id),
        reverse=True,
    )
    if not done:
        return None

    curr = done[0]
    muscle = primary_muscle(curr)
    prev: Optional[SessionSnap] = None
    for s in done[1:]:
        if muscle and muscle in muscles_from_session(s):
            prev = s
            break
        if not muscle and s.split_label and curr.split_label and s.split_label == curr.split_label:
            prev = s
            break

    curr_tops = _tops_by_exercise(curr, muscle)
    prev_tops = _tops_by_exercise(prev, muscle) if prev else {}

    # preserve first-seen exercise order from current session
    order: list[str] = []
    for s in curr.sets:
        if s.exercise_name not in order and s.exercise_name in curr_tops:
            order.append(s.exercise_name)

    lifts: list[dict[str, Any]] = []
    for name in order[:8]:
        c = curr_tops[name]
        p = prev_tops.get(name)
        cw = _effective_weight(c)
        cr = c.actual_reps
        pw = _effective_weight(p) if p else None
        pr = p.actual_reps if p else None

        delta_kind = "new"
        delta_label = "首次"
        weight_delta: Optional[float] = None
        reps_delta: Optional[int] = None

        if p:
            if cw is not None and pw is not None:
                weight_delta = round(cw - pw, 2)
                if weight_delta > 0.01:
                    delta_kind = "up"
                    delta_label = f"+{weight_delta:g}kg"
                elif weight_delta < -0.01:
                    delta_kind = "down"
                    delta_label = f"{weight_delta:g}kg"
                else:
                    weight_delta = 0.0
                    if cr is not None and pr is not None and cr != pr:
                        reps_delta = cr - pr
                        if reps_delta > 0:
                            delta_kind = "up"
                            delta_label = f"+{reps_delta}次"
                        else:
                            delta_kind = "down"
                            delta_label = f"{reps_delta}次"
                    else:
                        delta_kind = "flat"
                        delta_label = "持平"
            elif cr is not None and pr is not None:
                reps_delta = cr - pr
                if reps_delta > 0:
                    delta_kind = "up"
                    delta_label = f"+{reps_delta}次"
                elif reps_delta < 0:
                    delta_kind = "down"
                    delta_label = f"{reps_delta}次"
                else:
                    delta_kind = "flat"
                    delta_label = "持平"

        load = _format_load(cw, cr)
        lifts.append(
            {
                "exercise_name": name,
                "load": load,
                "weight": cw,
                "reps": cr,
                "prev_load": _format_load(pw, pr) if p else None,
                "delta_kind": delta_kind,
                "delta_label": delta_label,
                "weight_delta": weight_delta,
                "reps_delta": reps_delta,
            }
        )

    done_sets = sum(1 for s in curr.sets if s.completed)
    total_sets = len(curr.sets)
    quality = _session_quality_label(curr, lifts)

    return {
        "session_id": curr.id,
        "session_date": curr.session_date.isoformat(),
        "split_label": curr.split_label,
        "muscle": muscle,
        "duration_minutes": curr.duration_minutes,
        "done_sets": done_sets,
        "total_sets": total_sets,
        "quality": quality,
        "prev_session_id": prev.id if prev else None,
        "prev_date": prev.session_date.isoformat() if prev else None,
        "lifts": lifts,
    }


def _format_load(weight: Optional[float], reps: Optional[int]) -> str:
    if weight is None and reps is None:
        return "—"
    if weight is None:
        return f"自重 × {reps}" if reps is not None else "自重"
    w = f"{weight:g}"
    if reps is None:
        return f"{w} kg"
    return f"{w} kg × {reps}"


def _session_quality_label(sess: SessionSnap, lifts: list[dict[str, Any]]) -> str:
    if sess.session_outcome == "有突破":
        return "有突破"
    up = sum(1 for x in lifts if x["delta_kind"] == "up")
    down = sum(1 for x in lifts if x["delta_kind"] == "down")
    done = sum(1 for s in sess.sets if s.completed)
    total = len(sess.sets) or 1
    pct = done / total
    if up > 0 and down == 0:
        return "超量恢复"
    if down > up and down >= 2:
        return "偏吃力"
    if pct >= 0.95:
        return "高效达标"
    if pct >= 0.7:
        return "基本完成"
    return "未打满"


def build_key_lifts(
    sessions: list[SessionSnap],
    stats: list[ExerciseStats],
    muscle_by_name: dict[str, str],
    today: date,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Top progressive lifts: prefer rising trend + recent weight climb vs ~30d ago."""
    cutoff = today - timedelta(days=30)
    # name -> chronological top sets
    history: dict[str, list[tuple[date, float, Optional[int]]]] = {}
    for sess in sorted(
        [s for s in sessions if s.status == "done"],
        key=lambda s: (s.session_date, s.id),
    ):
        tops = _tops_by_exercise(sess)
        for name, top in tops.items():
            w = _effective_weight(top)
            if w is None:
                continue
            history.setdefault(name, []).append((sess.session_date, w, top.actual_reps))

    stat_map = {s.exercise_name: s for s in stats}
    candidates: list[dict[str, Any]] = []

    for name, points in history.items():
        if not points:
            continue
        last_date, last_w, last_r = points[-1]
        # earliest point in window, or first overall if none
        window = [p for p in points if p[0] >= cutoff]
        baseline = window[0] if window else points[0]
        base_w = baseline[1]
        delta = round(last_w - base_w, 2)
        st = stat_map.get(name)
        trend = st.trend if st else ("↑" if delta > 0.01 else "→" if abs(delta) <= 0.01 else "↓")
        is_pr = bool(st and st.best_weight is not None and abs((st.best_weight or 0) - last_w) < 0.01)

        # score: rising first, then absolute delta, then recency
        score = 0.0
        if trend == "↑" or delta > 0.01:
            score += 100
        if is_pr:
            score += 40
        score += min(40.0, abs(delta) * 4)
        score += max(0, 14 - (today - last_date).days)

        candidates.append(
            {
                "exercise_name": name,
                "muscle": muscle_by_name.get(name),
                "load": _format_load(last_w, last_r),
                "weight": last_w,
                "reps": last_r,
                "delta_kg": delta,
                "delta_label": (
                    f"较30天前 +{delta:g}kg"
                    if delta > 0.01
                    else f"较30天前 {delta:g}kg"
                    if delta < -0.01
                    else "较30天前持平"
                ),
                "trend": trend,
                "is_pr": is_pr,
                "last_date": last_date.isoformat(),
                "_score": score,
            }
        )

    # fill muscle from session tags if missing
    for c in candidates:
        if c["muscle"]:
            continue
        for sess in sessions:
            for s in sess.sets:
                if s.exercise_name == c["exercise_name"] and s.muscle:
                    c["muscle"] = s.muscle
                    break
            if c["muscle"]:
                break

    candidates.sort(key=lambda x: (-x["_score"], x["exercise_name"]))
    out = []
    for c in candidates[:limit]:
        c.pop("_score", None)
        out.append(c)
    return out


def build_headline(
    week: dict[str, Any],
    pulse: list[dict[str, Any]],
    compare: Optional[dict[str, Any]],
    lifts: list[dict[str, Any]],
) -> str:
    parts: list[str] = []

    if compare and compare.get("lifts"):
        muscle = compare.get("muscle") or compare.get("split_label") or "训练"
        up = [x for x in compare["lifts"] if x["delta_kind"] == "up"]
        down = [x for x in compare["lifts"] if x["delta_kind"] == "down"]
        if up and not down:
            parts.append(f"{muscle}主项较上次上涨（{up[0]['exercise_name']} {up[0]['delta_label']}）")
        elif up and down:
            parts.append(f"{muscle}有涨有掉 · {up[0]['exercise_name']}{up[0]['delta_label']}")
        elif down:
            parts.append(f"{muscle}较上次偏沉 · {down[0]['exercise_name']} {down[0]['delta_label']}")
        else:
            parts.append(f"{muscle}较上次重量持平")

    overdue = [p for p in pulse if p["status"] == "overdue"]
    if overdue:
        o = overdue[0]
        parts.append(f"{o['muscle']}已 {o['days_since']} 天未练")

    rising = [x for x in lifts if x.get("trend") == "↑" or (x.get("delta_kg") or 0) > 0]
    if rising and not parts:
        r = rising[0]
        parts.append(f"{r['exercise_name']} {r['delta_label']}")

    if not parts:
        td = week.get("trained_days") or 0
        target = week.get("target_days") or 4
        if td == 0:
            return "本周还没开练"
        return f"本周已练 {td}/{target} 天"

    return "；".join(parts[:2])


def _to_snap(sess: TrainingSession, sets: list[TrainingSetLog]) -> SessionSnap:
    return SessionSnap(
        id=sess.id or 0,
        session_date=sess.session_date,
        split_label=sess.split_label,
        status=sess.status,
        duration_minutes=sess.duration_minutes,
        session_outcome=sess.session_outcome,
        sets=[
            SetSnap(
                exercise_name=s.exercise_name,
                muscle=s.muscle,
                set_index=s.set_index,
                actual_weight=s.actual_weight,
                actual_reps=s.actual_reps,
                target_weight=s.target_weight,
                completed=bool(s.completed),
            )
            for s in sets
        ],
    )


def build_dashboard(session: Session, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    profile = session.exec(select(Profile).limit(1)).first()
    target_days = profile.days_per_week if profile else 4

    from sqlalchemy import or_

    rows = list(
        session.exec(
            select(TrainingSession)
            .where(
                or_(
                    TrainingSession.status == "done",
                    TrainingSession.status == "active",
                )
            )
            .order_by(col(TrainingSession.session_date).desc(), col(TrainingSession.id).desc())
            .limit(60)
        ).all()
    )
    snaps: list[SessionSnap] = []
    for sess in rows:
        sets = list(
            session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == sess.id)).all()
        )
        snaps.append(_to_snap(sess, sets))

    stats = list(session.exec(select(ExerciseStats)).all())
    mine = {m.name: m.muscle for m in session.exec(select(MyExercise)).all()}

    week = build_week_rhythm(snaps, target_days, today)
    pulse = build_muscle_pulse(snaps, today)
    compare = build_session_compare(snaps)
    lifts = build_key_lifts(snaps, stats, mine, today)
    headline = build_headline(week, pulse, compare, lifts)

    return {
        "as_of": today.isoformat(),
        "headline": headline,
        "week": week,
        "muscle_pulse": pulse,
        "session_compare": compare,
        "key_lifts": lifts,
    }
