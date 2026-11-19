"""计划模板：列表 / 详情 / 按板块展开成今日草稿。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.exercises_catalog import (
    is_banned_for_injuries,
    retrieve_candidates,
    suggest_weight_from_stats,
)
from app.models import (
    Exercise,
    ExerciseStats,
    PlanBlock,
    PlanExercise,
    PlanTemplate,
    TrainingSession,
    utcnow,
)
from app.slot_roles import infer_slot_roles, is_core_movement, normalize_slot_roles
from app.taxonomy import canonicalize_exercise
from app.tenancy import current_user_id, get_current_profile

# 臂细分：优先信 sub_region 受控枚举（见 admin_editor._SUB_BY_MUSCLE「臂」）
_PUSH_ARM_SUB = ("肱三头肌",)
_PULL_ARM_SUB = ("肱二头肌",)

# 奥举 / 杂技平衡：大众健身房框架课默认降权过滤（见 docs/09 A2）
_NICHE_LIFT_MARKERS = (
    "抓举",
    "挺举",
    "翻举",
    "上送",
    "高翻",
    "悬垂抓",
    "肌肉抓",
    "力量抓",
    "力量挺",
    "架上抓",
    "抓举平衡",
    "挺举预蹲",
    "弗兰肯斯坦",
    "过头深蹲",
)
_NICHE_BALANCE_MARKERS = ("平衡板", "平衡垫", "平衡三点")
_MAIN_GEAR_SCORE = {
    "自由重量": 10,
    "固定器械": 8,
    "器械": 8,
    "绳索": 4,
    "自重": -8,
}


ROLE_LABEL = {
    "main": "主项",
    "assist": "辅助",
    "isolation": "孤立",
    "warmup": "热身",
}

LEVEL_LABEL = {
    "beginner": "新手",
    "intermediate": "进阶",
    "advanced": "强化",
}


def _minutes_label(mn: int | None, mx: int | None) -> str | None:
    if mn is None and mx is None:
        return None
    if mn is not None and mx is not None:
        if mn == mx:
            return f"{mn} 分钟"
        return f"{mn}-{mx} 分钟"
    return f"{mn or mx} 分钟"


def _split_line(tpl: PlanTemplate) -> str:
    if tpl.split_summary:
        return tpl.split_summary
    tags = [str(t) for t in (tpl.muscle_tags or []) if t]
    return " · ".join(tags) if tags else ""


def _scene_tag_of(session: Session, tpl: PlanTemplate, block_count: int | None = None) -> str | None:
    """优先用落库 scene_tag；空则按作者/难度/板块数兜底派生。"""
    if tpl.scene_tag:
        return tpl.scene_tag
    author = (tpl.author or "").strip()
    if author and author not in ("Gym Coach", "GymCoach"):
        return "博主同款"
    if tpl.level == "beginner":
        return "新手入门"
    n = block_count
    if n is None:
        n = len(
            session.exec(select(PlanBlock.id).where(PlanBlock.template_id == tpl.id)).all()
        )
    if n == 1:
        return "单部位专项"
    if tpl.days_per_week == 3 and n >= 3:
        return "三分化"
    if tpl.days_per_week == 4 and n >= 4:
        return "四分化"
    if tpl.days_per_week == 5 and n >= 5:
        return "五分化"
    return None


def _template_card(
    session: Session, tpl: PlanTemplate, *, block_count: int | None = None
) -> dict[str, Any]:
    return {
        "id": tpl.id,
        "title": tpl.title,
        "subtitle": tpl.subtitle,
        "author": tpl.author,
        "badge_label": tpl.badge_label,
        "template_type": tpl.template_type,
        "scene_tag": _scene_tag_of(session, tpl, block_count),
        "level": tpl.level,
        "level_label": LEVEL_LABEL.get(tpl.level or "", tpl.level),
        "days_per_week": tpl.days_per_week,
        "minutes_min": tpl.minutes_min,
        "minutes_max": tpl.minutes_max,
        "minutes_label": _minutes_label(tpl.minutes_min, tpl.minutes_max),
        "muscle_tags": list(tpl.muscle_tags or []),
        "split_summary": _split_line(tpl),
        "gear_tags": list(tpl.gear_tags or []),
        "cover_url": tpl.cover_url,
        "description": tpl.description,
        "is_published": tpl.is_published,
        "sort_order": tpl.sort_order,
    }


def list_published_plans(
    session: Session,
    *,
    template_type: str | None = None,
    scene_tag: str | None = None,
    muscle: str | None = None,
    level: str | None = None,
) -> list[dict[str, Any]]:
    q = select(PlanTemplate).where(PlanTemplate.is_published == True)  # noqa: E712
    if template_type in ("framework", "fixed"):
        q = q.where(PlanTemplate.template_type == template_type)
    if level:
        q = q.where(PlanTemplate.level == level)
    rows = list(session.exec(q.order_by(col(PlanTemplate.sort_order), col(PlanTemplate.id))).all())
    out: list[dict[str, Any]] = []
    for tpl in rows:
        if muscle:
            tags = [str(t) for t in (tpl.muscle_tags or [])]
            if muscle not in tags:
                continue
        blocks = session.exec(
            select(PlanBlock)
            .where(PlanBlock.template_id == tpl.id)
            .order_by(col(PlanBlock.order_index), col(PlanBlock.id))
        ).all()
        card = _template_card(session, tpl, block_count=len(blocks))
        card["block_count"] = len(blocks)
        if scene_tag and scene_tag != "全部":
            if card.get("scene_tag") != scene_tag:
                continue
        out.append(card)
    return out


def get_plan_detail(session: Session, plan_id: str) -> dict[str, Any]:
    """详情预览：空槽位当场按部位+角色配好动作名，不把「槽位·主项」甩给用户。"""
    tpl = session.get(PlanTemplate, plan_id)
    if not tpl or not tpl.is_published:
        raise HTTPException(status_code=404, detail="计划不存在或未发布")
    detail = _template_card(session, tpl)
    profile = get_current_profile(session)
    injuries = list(getattr(profile, "injuries", None) or []) if profile else []
    avoid = list(getattr(profile, "avoid_exercises", None) or []) if profile else []

    blocks_out: list[dict[str, Any]] = []
    blocks = session.exec(
        select(PlanBlock)
        .where(PlanBlock.template_id == plan_id)
        .order_by(col(PlanBlock.order_index), col(PlanBlock.id))
    ).all()
    for block in blocks:
        exercises = session.exec(
            select(PlanExercise)
            .where(PlanExercise.block_id == block.id)
            .order_by(col(PlanExercise.order_index), col(PlanExercise.id))
        ).all()
        used_names: set[str] = set()
        used_gears: set[str] = set()
        used_sub_regions: set[str] = set()
        ex_rows: list[dict[str, Any]] = []
        for ex in exercises:
            name = ex.exercise_name
            exercise_id = ex.exercise_id
            preview_filled = False
            # 框架空槽 / 仅有角色：预览时就配好，和「练这场」同一套检索
            if not name and not exercise_id:
                picked = _resolve_exercise_row(
                    session,
                    tpl=tpl,
                    block=block,
                    row=ex,
                    injuries=injuries,
                    avoid=avoid,
                    used_names=used_names,
                    used_gears=used_gears,
                    used_sub_regions=used_sub_regions,
                )
                name = picked.get("name")
                exercise_id = picked.get("exercise_id") or exercise_id
                preview_filled = bool(name)
                if picked.get("gear"):
                    used_gears.add(str(picked["gear"]))
                if picked.get("sub_region"):
                    used_sub_regions.add(str(picked["sub_region"]))
            if name:
                used_names.add(canonicalize_exercise(str(name)))
            thumb = _thumb_url(session, exercise_id=exercise_id, name=name)
            ex_rows.append(
                {
                    "id": ex.id,
                    "order_index": ex.order_index,
                    "exercise_id": exercise_id,
                    "exercise_name": name,
                    "role": ex.role,
                    "role_label": ROLE_LABEL.get(ex.role, ex.role),
                    "lock_level": ex.lock_level,
                    "target_muscle": getattr(ex, "target_muscle", None),
                    "target_sets": ex.target_sets,
                    "target_reps": ex.target_reps,
                    "warmup_sets": ex.warmup_sets or 0,
                    "alternatives": list(ex.alternatives or []),
                    "note": ex.note,
                    "thumb_url": thumb,
                    "pending": not bool(name),
                    "preview_filled": preview_filled,
                }
            )
        blocks_out.append(
            {
                "id": block.id,
                "order_index": block.order_index,
                "title": block.title,
                "muscles": list(block.muscles or []),
                "minutes_min": block.minutes_min,
                "minutes_max": block.minutes_max,
                "minutes_label": _minutes_label(block.minutes_min, block.minutes_max),
                "cover_url": block.cover_url,
                "note": block.note,
                "exercises": ex_rows,
            }
        )
    detail["blocks"] = blocks_out
    detail["block_count"] = len(blocks_out)
    detail["scene_tag"] = _scene_tag_of(session, tpl, len(blocks_out))
    # 跟练态：详情页可直接标「本周已练 / 推荐今日练」
    following = get_following_progress(session)
    detail["is_following"] = following.get("active_plan_id") == plan_id
    detail["week_progress"] = following.get("week") if detail["is_following"] else None
    return detail


def _week_bounds(day: date | None = None) -> tuple[date, date]:
    """自然周：周一 00:00 至周日。"""
    day = day or date.today()
    start = day - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return start, end


def _sessions_for_user():
    stmt = select(TrainingSession)
    uid = current_user_id()
    if uid is not None:
        stmt = stmt.where(TrainingSession.user_id == uid)
    return stmt


def follow_plan(session: Session, plan_id: str) -> dict[str, Any]:
    tpl = session.get(PlanTemplate, plan_id)
    if not tpl or not tpl.is_published:
        raise HTTPException(status_code=404, detail="计划不存在或未发布")
    profile = get_current_profile(session)
    if not profile:
        raise HTTPException(status_code=400, detail="请先完善个人资料")
    profile.active_plan_id = plan_id
    profile.active_plan_started_at = utcnow()
    profile.updated_at = utcnow()
    session.add(profile)
    session.commit()
    return get_following_progress(session)


def unfollow_plan(session: Session) -> dict[str, Any]:
    profile = get_current_profile(session)
    if not profile:
        raise HTTPException(status_code=400, detail="请先完善个人资料")
    profile.active_plan_id = None
    profile.active_plan_started_at = None
    profile.updated_at = utcnow()
    session.add(profile)
    session.commit()
    return get_following_progress(session)


def get_following_progress(session: Session, day: date | None = None) -> dict[str, Any]:
    """本周跟练进度：按自然周已练板块推算 next_block，绝不锁死。"""
    day = day or date.today()
    profile = get_current_profile(session)
    active_id = getattr(profile, "active_plan_id", None) if profile else None
    started_at = getattr(profile, "active_plan_started_at", None) if profile else None
    empty = {
        "active_plan_id": None,
        "active_plan_started_at": None,
        "plan": None,
        "week": {
            "completed_block_ids": [],
            "next_block": None,
            "week_cycle_done": False,
            "total_blocks": 0,
            "completed_count": 0,
            "today_block_id": None,
            "progress_label": None,
        },
    }
    if not active_id:
        return empty

    tpl = session.get(PlanTemplate, active_id)
    if not tpl or not tpl.is_published:
        # 计划被下架：清空跟练，避免脏指针
        if profile:
            profile.active_plan_id = None
            profile.active_plan_started_at = None
            profile.updated_at = utcnow()
            session.add(profile)
            session.commit()
        return empty

    blocks = list(
        session.exec(
            select(PlanBlock)
            .where(PlanBlock.template_id == active_id)
            .order_by(col(PlanBlock.order_index), col(PlanBlock.id))
        ).all()
    )
    week_start, week_end = _week_bounds(day)
    rows = list(
        session.exec(
            _sessions_for_user()
            .where(TrainingSession.plan_template_id == active_id)
            .where(TrainingSession.session_date >= week_start)
            .where(TrainingSession.session_date <= week_end)
            .where(or_(TrainingSession.status == "active", TrainingSession.status == "done"))
            .order_by(col(TrainingSession.session_date), col(TrainingSession.id))
        ).all()
    )

    completed_ids: list[int] = []
    today_block_id: int | None = None
    seen: set[int] = set()
    for sess in rows:
        bid = sess.plan_block_id
        if bid is None:
            continue
        if sess.session_date == day:
            today_block_id = bid
        if bid not in seen:
            seen.add(bid)
            completed_ids.append(bid)

    next_block = None
    week_cycle_done = False
    for block in blocks:
        if block.id not in seen:
            next_block = block
            break
    if blocks and next_block is None:
        week_cycle_done = True
        next_block = blocks[0]

    def _block_brief(block: PlanBlock | None) -> dict[str, Any] | None:
        if not block:
            return None
        ex_rows = list(
            session.exec(
                select(PlanExercise)
                .where(PlanExercise.block_id == block.id)
                .order_by(col(PlanExercise.order_index), col(PlanExercise.id))
            ).all()
        )
        preview_names: list[str] = []
        for ex in ex_rows:
            if ex.exercise_name:
                preview_names.append(ex.exercise_name)
            if len(preview_names) >= 4:
                break
        # 框架空槽：详情预览逻辑太重，这里只返回已有名；前端可再拉详情补
        return {
            "id": block.id,
            "order_index": block.order_index,
            "title": block.title,
            "muscles": list(block.muscles or []),
            "minutes_label": _minutes_label(block.minutes_min, block.minutes_max),
            "cover_url": block.cover_url,
            "exercise_count": len(ex_rows),
            "preview_names": preview_names,
        }

    total = len(blocks)
    done_n = len(completed_ids)
    order_of_next = None
    if next_block:
        for i, b in enumerate(blocks, start=1):
            if b.id == next_block.id:
                order_of_next = i
                break
    progress_label = None
    if total > 0 and order_of_next is not None:
        progress_label = f"本周第 {order_of_next}/{total} 练"

    card = _template_card(session, tpl, block_count=total)
    card["block_count"] = total

    return {
        "active_plan_id": active_id,
        "active_plan_started_at": started_at.isoformat() if started_at else None,
        "plan": card,
        "week": {
            "completed_block_ids": completed_ids,
            "next_block": _block_brief(next_block),
            "week_cycle_done": week_cycle_done,
            "total_blocks": total,
            "completed_count": done_n,
            "today_block_id": today_block_id,
            "progress_label": progress_label,
        },
    }


def _thumb_url(
    session: Session, *, exercise_id: str | None, name: str | None = None
) -> str | None:
    sku = None
    if exercise_id:
        sku = session.get(Exercise, exercise_id)
    if not sku and name:
        sku = session.exec(select(Exercise).where(Exercise.name_zh == name)).first()
    if not sku or not sku.image_start:
        return None
    path = sku.image_start
    return path if path.startswith("/static/") else f"/static/exercises/{path}"


def expand_plan_block(session: Session, plan_id: str, block_id: int) -> dict[str, Any]:
    tpl = session.get(PlanTemplate, plan_id)
    if not tpl or not tpl.is_published:
        raise HTTPException(status_code=404, detail="计划不存在或未发布")
    block = session.get(PlanBlock, block_id)
    if not block or block.template_id != plan_id:
        raise HTTPException(status_code=404, detail="板块不存在")

    rows = list(
        session.exec(
            select(PlanExercise)
            .where(PlanExercise.block_id == block_id)
            .order_by(col(PlanExercise.order_index), col(PlanExercise.id))
        ).all()
    )
    if not rows:
        raise HTTPException(status_code=400, detail="该板块还没有动作行")

    profile = get_current_profile(session)
    injuries = list(getattr(profile, "injuries", None) or []) if profile else []
    avoid = list(getattr(profile, "avoid_exercises", None) or []) if profile else []
    experience = (profile.experience if profile and profile.experience else "进阶") or "进阶"

    used_names: set[str] = set()
    used_gears: set[str] = set()
    used_sub_regions: set[str] = set()
    items: list[dict[str, Any]] = []

    for idx, row in enumerate(rows):
        picked = _resolve_exercise_row(
            session,
            tpl=tpl,
            block=block,
            row=row,
            injuries=injuries,
            avoid=avoid,
            used_names=used_names,
            used_gears=used_gears,
            used_sub_regions=used_sub_regions,
        )
        name = picked.get("name") or ""
        pending = not bool(name)
        if name:
            used_names.add(canonicalize_exercise(name))
            if picked.get("gear"):
                used_gears.add(str(picked["gear"]))
            if picked.get("sub_region"):
                used_sub_regions.add(str(picked["sub_region"]))

        weight = None
        if name and not pending:
            weight = _suggest_weight(session, name, experience)

        sets = row.target_sets or 3
        reps = row.target_reps or "8-12"
        muscle = picked.get("muscle") or _primary_muscle(block, row)
        note_bits = []
        if row.note:
            note_bits.append(str(row.note))
        if picked.get("swap_note"):
            note_bits.append(str(picked["swap_note"]))
        if pending:
            note_bits.append("待补充")

        subtitle_parts = [f"{sets}×{reps}"]
        if weight is not None:
            subtitle_parts.append(f"建议 {weight}kg")
        if row.warmup_sets:
            subtitle_parts.append(f"热身 {row.warmup_sets}")

        items.append(
            {
                "id": f"plan-{block_id}-{row.id or idx}",
                "title": name or f"槽位·{ROLE_LABEL.get(row.role, row.role)}",
                "subtitle": " · ".join(subtitle_parts),
                "selected": not pending,
                "meta": {
                    "sets": sets,
                    "reps": reps,
                    "weight": weight,
                    "muscle": muscle,
                    "role": row.role,
                    "warmup_sets": row.warmup_sets or 0,
                    "exercise_id": picked.get("exercise_id"),
                    "lock_level": row.lock_level,
                    "pending": pending,
                    "note": "；".join(note_bits) if note_bits else None,
                    "gear": picked.get("gear"),
                    "sub_region": picked.get("sub_region"),
                },
            }
        )

    title = f"{tpl.title} · {block.title}"
    return {
        "card": {
            "kind": "card",
            "card_type": "training_draft",
            "title": title,
            "status": "draft",
            "items": items,
            "actions": ["adopt", "edit"],
            "meta": {
                "plan_template_id": tpl.id,
                "plan_block_id": block.id,
                "plan_type": tpl.template_type,
                "split_label": block.title,
                "source": "plan_expand",
            },
        }
    }


def _primary_muscle(block: PlanBlock, row: PlanExercise) -> str:
    target = (getattr(row, "target_muscle", None) or "").strip()
    if target:
        return target
    muscles = [str(m) for m in (block.muscles or []) if m]
    if not muscles:
        return "全身"
    # 臂日槽位默认落到臂
    if row.role == "isolation" and "臂" in muscles:
        return "臂"
    return muscles[0]


def _arm_bias_for_block(block: PlanBlock) -> str | None:
    """推日→三头；拉日→二头。"""
    muscles = {str(m) for m in (block.muscles or []) if m}
    title = block.title or ""
    if "背" in muscles or "背" in title or "拉" in title:
        return "pull"
    if ("胸" in muscles or "肩" in muscles) or any(x in title for x in ("胸", "肩", "推", "三头")):
        return "push"
    return None


def _matches_arm_bias(cand: dict[str, Any], bias: str | None) -> bool:
    """推日臂→三头；拉日臂→二头。只看 sub_region 枚举；未填亚区则不强行按名字猜。"""
    if not bias:
        return True
    sub = str(cand.get("sub_region") or "")
    if not sub:
        return True  # 无亚区时不误杀；靠主练肌群分 + 多样性排序
    want = _PUSH_ARM_SUB if bias == "push" else _PULL_ARM_SUB
    return any(s in sub for s in want)


def _is_niche_gym_lift(cand: dict[str, Any]) -> bool:
    """奥举 / 平衡杂技：框架配课默认不当大众主项。"""
    name = str(cand.get("name") or "")
    modality = str(cand.get("modality") or "")
    category = str(cand.get("category") or cand.get("gear") or "")
    if modality == "灵活性" and any(k in name for k in _NICHE_BALANCE_MARKERS):
        return True
    if any(k in name for k in _NICHE_LIFT_MARKERS):
        return True
    if any(k in name for k in _NICHE_BALANCE_MARKERS):
        return True
    # category 偶发带 olympic 英文标签
    low = f"{category} {modality}".lower()
    if "olympic" in low or "weightlifting" in low:
        return True
    return False


def _suggest_weight(session: Session, name: str, experience: str) -> float | None:
    uid = current_user_id()
    q = select(ExerciseStats).where(ExerciseStats.exercise_name == canonicalize_exercise(name))
    if uid is not None:
        q = q.where(ExerciseStats.user_id == uid)
    else:
        q = q.where(ExerciseStats.user_id == None)  # noqa: E711
    stats = session.exec(q).first()
    if not stats:
        return None
    return suggest_weight_from_stats(
        stats.last_weight,
        experience,
        last_feeling=stats.last_feeling,
        last_outcome=stats.last_outcome,
    )


def _resolve_exercise_row(
    session: Session,
    *,
    tpl: PlanTemplate,
    block: PlanBlock,
    row: PlanExercise,
    injuries: list[str],
    avoid: list[str],
    used_names: set[str],
    used_gears: set[str],
    used_sub_regions: set[str],
) -> dict[str, Any]:
    """成品直取；框架检索填充。命中伤病/避免则尝试 alternatives。"""
    candidates: list[dict[str, Any]] = []

    if row.exercise_id:
        sku = session.get(Exercise, row.exercise_id)
        if sku:
            candidates.append(_from_sku(sku))
    if row.exercise_name:
        candidates.append(
            {
                "name": row.exercise_name,
                "exercise_id": row.exercise_id,
                "muscle": _primary_muscle(block, row),
                "gear": None,
                "sub_region": None,
            }
        )
    for alt in row.alternatives or []:
        if isinstance(alt, str) and alt.strip():
            candidates.append(
                {
                    "name": alt.strip(),
                    "exercise_id": None,
                    "muscle": _primary_muscle(block, row),
                    "gear": None,
                    "sub_region": None,
                }
            )

    # 框架型 / 空槽：从动作库检索（有 target_muscle 则单部位抽，避免胸肩三头混池）
    if tpl.template_type == "framework" or not any(c.get("name") for c in candidates):
        target = (getattr(row, "target_muscle", None) or "").strip()
        slot_muscles = [target] if target else [str(m) for m in (block.muscles or []) if m]
        retrieved = _retrieve_for_slot(
            session,
            muscles=slot_muscles,
            role=row.role,
            injuries=injuries,
            exclude=list(used_names),
            avoid=avoid,
            arm_bias=_arm_bias_for_block(block) if target == "臂" or "臂" in slot_muscles else None,
            allow_core=("核心" in slot_muscles),
        )
        candidates.extend(retrieved)

    avoid_canon = {canonicalize_exercise(a) for a in avoid if a}

    def _ok(cand: dict[str, Any], *, allow_niche: bool = False) -> bool:
        name = str(cand.get("name") or "").strip()
        if not name:
            return False
        canon = canonicalize_exercise(name)
        if canon in used_names or canon in avoid_canon:
            return False
        if is_banned_for_injuries(name, injuries):
            return False
        if not allow_niche and _is_niche_gym_lift(cand):
            return False
        return True

    valid = [c for c in candidates if _ok(c)]
    # 伤病/过滤过严时再放宽奥举池，避免整槽空白
    if not valid:
        valid = [c for c in candidates if _ok(c, allow_niche=True)]
    isolation_fallback_note = None
    if not valid and row.role == "isolation":
        # A3：孤立无候选时退到同肌群辅助
        assist_pool = _retrieve_for_slot(
            session,
            muscles=[_primary_muscle(block, row)],
            role="assist",
            injuries=injuries,
            exclude=list(used_names),
            avoid=avoid,
            arm_bias=_arm_bias_for_block(block)
            if _primary_muscle(block, row) == "臂"
            else None,
            allow_core=("核心" == _primary_muscle(block, row)),
        )
        valid = [c for c in assist_pool if _ok(c)]
        if valid:
            isolation_fallback_note = "孤立动作暂缺，已用辅助动作替代"

    if not valid:
        if row.exercise_name:
            return {
                "name": row.exercise_name,
                "exercise_id": row.exercise_id,
                "muscle": _primary_muscle(block, row),
                "gear": None,
                "sub_region": None,
                "swap_note": "伤病/器械受限，暂无合适替代，请自行更换",
            }
        return {"name": None, "swap_note": "待补充"}

    # 成品：按声明顺序取第一个可用（原动作 → 备选）
    if tpl.template_type == "fixed":
        best = valid[0]
        swap_note = None
        if row.exercise_name and canonicalize_exercise(best["name"]) != canonicalize_exercise(
            row.exercise_name
        ):
            swap_note = f"已从「{row.exercise_name}」降级替换"
        return {**best, "swap_note": swap_note}

    # 框架：主练肌群优先 + 臂推/拉细分 + 器械/亚区多样性 + coach_core 强优先
    target = (getattr(row, "target_muscle", None) or "").strip()
    arm_bias = _arm_bias_for_block(block) if target == "臂" else None
    role = (row.role or "assist").strip()
    for cand in valid:
        score = 0
        if target and cand.get("muscle") == target:
            score += 20
        if target == "臂" and _matches_arm_bias(cand, arm_bias):
            score += 15
        gear = cand.get("gear")
        sub = cand.get("sub_region")
        if gear and gear not in used_gears:
            score += 3
        if sub and sub not in used_sub_regions:
            score += 2
        if cand.get("coach_core"):
            # 主项强绑常用池；辅助/孤立也明显加分
            score += 40 if role == "main" else 18
        elif role == "main":
            score -= 25  # 非 core 不当默认主项
        if role == "main":
            gear_key = str(cand.get("gear") or cand.get("category") or "")
            score += int(_MAIN_GEAR_SCORE.get(gear_key, 0))
        if _is_niche_gym_lift(cand):
            score -= 80
        cand["_score"] = score
    valid.sort(key=lambda c: int(c.get("_score") or 0), reverse=True)
    best = valid[0]
    # 主项：优先非奥举的 coach_core；再优先自由重量/器械
    if role == "main":
        core_pool = [c for c in valid if c.get("coach_core") and not _is_niche_gym_lift(c)]
        if core_pool:
            core_pool.sort(key=lambda c: int(c.get("_score") or 0), reverse=True)
            best = core_pool[0]
    return {**best, "swap_note": isolation_fallback_note}


def _from_sku(sku: Exercise) -> dict[str, Any]:
    return {
        "name": sku.name_zh,
        "exercise_id": sku.id,
        "muscle": sku.muscle,
        "gear": sku.gear,
        "sub_region": sku.sub_region,
        "coach_core": bool(sku.coach_core),
    }


def _retrieve_for_slot(
    session: Session,
    *,
    muscles: list[str],
    role: str,
    injuries: list[str],
    exclude: list[str],
    avoid: list[str],
    arm_bias: str | None = None,
    allow_core: bool = False,
) -> list[dict[str, Any]]:
    """内存目录检索 + DB slot_roles / 亚区；主练肌群强优先。"""
    pool = retrieve_candidates(
        muscles=muscles or None,
        modalities=["抗阻"],
        injuries=injuries,
        exclude=exclude,
        limit=50,
        primary_muscle_first=True,
        drop_synergy_if_primary_ge=8,
    )
    avoid_canon = {canonicalize_exercise(a) for a in avoid if a}
    name_to_meta: dict[str, dict[str, Any]] = {}
    if pool:
        names = [p["name"] for p in pool[:50]]
        db_rows = session.exec(select(Exercise).where(col(Exercise.name_zh).in_(names))).all()
        for ex in db_rows:
            name_to_meta[ex.name_zh] = {
                "slot_roles": normalize_slot_roles(ex.slot_roles),
                "sub_region": ex.sub_region,
                "movement_pattern": ex.movement_pattern,
                "muscle": ex.muscle,
            }

    def _collect(wanted_role: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in pool:
            name = item["name"]
            if canonicalize_exercise(name) in avoid_canon:
                continue
            meta = name_to_meta.get(name) or {}
            muscle_v = meta.get("muscle") or item.get("muscle")
            pattern_v = meta.get("movement_pattern")
            if not allow_core and is_core_movement(movement_pattern=pattern_v, muscle=muscle_v):
                continue
            roles = list(meta.get("slot_roles") or [])
            # slot_roles 空：用枚举字段推断（仍不看动作名）
            if not roles:
                roles = infer_slot_roles(
                    movement_pattern=pattern_v,
                    muscle=muscle_v,
                    coach_core=bool(item.get("coach_core")),
                )
            # 热身不进主项/辅助/孤立竞争池
            if wanted_role != "warmup" and "warmup" in roles and "main" not in roles and "assist" not in roles and "isolation" not in roles:
                continue
            if wanted_role != "warmup" and roles == ["warmup"]:
                continue
            if roles and wanted_role not in roles:
                # 主项可吃辅助；孤立也可吃辅助（movement_pattern 大量为空时否则配空）
                if wanted_role == "main" and "assist" in roles:
                    pass
                elif wanted_role == "isolation" and "assist" in roles:
                    pass
                else:
                    continue
            if wanted_role == "isolation" and not allow_core and is_core_movement(
                movement_pattern=pattern_v,
                muscle=muscle_v,
            ):
                continue
            cand = {
                "name": name,
                "exercise_id": item.get("id"),
                "muscle": item.get("muscle") or (muscles[0] if muscles else "全身"),
                "gear": item.get("category") or item.get("gear"),
                "category": item.get("category"),
                "modality": item.get("modality"),
                "sub_region": meta.get("sub_region") or item.get("sub_region"),
                "coach_core": bool(item.get("coach_core")),
            }
            if _is_niche_gym_lift(cand) and wanted_role == "main":
                continue
            if arm_bias and not _matches_arm_bias(cand, arm_bias):
                cand["_arm_mismatch"] = True
            rows.append(cand)
        return rows

    out = _collect(role)
    # A3：孤立槽位无命中时，同池退到 assist
    if not out and role == "isolation":
        out = _collect("assist")

    if arm_bias:
        matched = [c for c in out if not c.get("_arm_mismatch")]
        if len(matched) >= 3:
            out = matched
        else:
            out = matched + [c for c in out if c.get("_arm_mismatch")]
    return out
