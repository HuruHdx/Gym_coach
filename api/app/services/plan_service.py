"""计划模板：列表 / 详情 / 按板块展开成今日草稿。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.exercises_catalog import (
    is_banned_for_injuries,
    retrieve_candidates,
    suggest_weight_from_stats,
)
from app.models import Exercise, ExerciseStats, PlanBlock, PlanExercise, PlanTemplate
from app.slot_roles import normalize_slot_roles
from app.taxonomy import canonicalize_exercise
from app.tenancy import current_user_id, get_current_profile


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


def _template_card(tpl: PlanTemplate) -> dict[str, Any]:
    return {
        "id": tpl.id,
        "title": tpl.title,
        "subtitle": tpl.subtitle,
        "author": tpl.author,
        "badge_label": tpl.badge_label,
        "template_type": tpl.template_type,
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
        card = _template_card(tpl)
        blocks = session.exec(
            select(PlanBlock)
            .where(PlanBlock.template_id == tpl.id)
            .order_by(col(PlanBlock.order_index), col(PlanBlock.id))
        ).all()
        card["block_count"] = len(blocks)
        out.append(card)
    return out


def get_plan_detail(session: Session, plan_id: str) -> dict[str, Any]:
    """详情预览：空槽位当场按部位+角色配好动作名，不把「槽位·主项」甩给用户。"""
    tpl = session.get(PlanTemplate, plan_id)
    if not tpl or not tpl.is_published:
        raise HTTPException(status_code=404, detail="计划不存在或未发布")
    detail = _template_card(tpl)
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
    return detail


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
    muscles = [str(m) for m in (block.muscles or []) if m]
    if not muscles:
        return "全身"
    # 臂日槽位默认落到臂
    if row.role == "isolation" and "臂" in muscles:
        return "臂"
    return muscles[0]


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

    # 框架型 / 空槽：从动作库检索
    if tpl.template_type == "framework" or not any(c.get("name") for c in candidates):
        retrieved = _retrieve_for_slot(
            session,
            muscles=[str(m) for m in (block.muscles or []) if m],
            role=row.role,
            injuries=injuries,
            exclude=list(used_names),
            avoid=avoid,
        )
        candidates.extend(retrieved)

    avoid_canon = {canonicalize_exercise(a) for a in avoid if a}

    def _ok(cand: dict[str, Any]) -> bool:
        name = str(cand.get("name") or "").strip()
        if not name:
            return False
        canon = canonicalize_exercise(name)
        if canon in used_names or canon in avoid_canon:
            return False
        if is_banned_for_injuries(name, injuries):
            return False
        return True

    valid = [c for c in candidates if _ok(c)]
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

    # 框架：器械 / 亚区多样性 + coach_core
    for cand in valid:
        score = 0
        gear = cand.get("gear")
        sub = cand.get("sub_region")
        if gear and gear not in used_gears:
            score += 3
        if sub and sub not in used_sub_regions:
            score += 2
        if cand.get("coach_core"):
            score += 1
        cand["_score"] = score
    valid.sort(key=lambda c: int(c.get("_score") or 0), reverse=True)
    return {**valid[0], "swap_note": None}


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
) -> list[dict[str, Any]]:
    """内存目录检索 + DB slot_roles 加权；兼顾器械/亚区多样性。"""
    pool = retrieve_candidates(
        muscles=muscles or None,
        modalities=["抗阻"],
        injuries=injuries,
        exclude=exclude,
        limit=40,
    )
    avoid_canon = {canonicalize_exercise(a) for a in avoid if a}
    # 可选：用 DB 的 slot_roles 抬权
    name_to_roles: dict[str, list[str]] = {}
    if pool:
        names = [p["name"] for p in pool[:40]]
        db_rows = session.exec(select(Exercise).where(col(Exercise.name_zh).in_(names))).all()
        for ex in db_rows:
            name_to_roles[ex.name_zh] = normalize_slot_roles(ex.slot_roles)

    out: list[dict[str, Any]] = []
    for item in pool:
        name = item["name"]
        if canonicalize_exercise(name) in avoid_canon:
            continue
        roles = name_to_roles.get(name) or []
        # 有角色标注时优先匹配；没有标注的仍可进候选（兼容未清洗库）
        if roles and role not in roles:
            # 主项可放宽到 assist；孤立/热身严格一点
            if not (role == "main" and "assist" in roles):
                continue
        out.append(
            {
                "name": name,
                "exercise_id": item.get("id"),
                "muscle": item.get("muscle") or (muscles[0] if muscles else "全身"),
                "gear": item.get("category") or item.get("gear"),
                "sub_region": item.get("sub_region"),
                "coach_core": bool(item.get("coach_core")),
            }
        )
    return out
