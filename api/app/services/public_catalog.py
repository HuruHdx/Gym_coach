"""C 端动作库只读：有效动作 + published 媒体。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, case, or_
from sqlmodel import Session, col, func, select

from app.models import Exercise, ExerciseAlias, ExerciseMedia
from app.services.admin_catalog import MEDIA_ROLES, media_url, _published_media_by_exercise


def thumb_for_exercise(ex: Exercise, media_map: dict[str, ExerciseMedia]) -> str | None:
    for role in ("start", "end", "demo", "tip", "highlight_video"):
        row = media_map.get(role)
        if row and row.url:
            return media_url(row.url)
    return media_url(ex.image_start) or media_url(ex.image_end)


def _public_list_item(ex: Exercise, media_map: dict[str, ExerciseMedia]) -> dict[str, Any]:
    return {
        "id": ex.id,
        "name_zh": ex.name_zh,
        "name_en": ex.name_en,
        "muscle": ex.muscle,
        "sub_region": ex.sub_region,
        "gear": ex.gear,
        "modality": ex.modality,
        "coach_core": bool(ex.coach_core),
        "thumb_url": thumb_for_exercise(ex, media_map),
    }


def list_public_exercises(
    session: Session,
    *,
    q: str | None = None,
    muscle: str | None = None,
    gear: str | None = None,
    modality: str | None = None,
    coach_core: bool | None = None,
    page: int = 1,
    page_size: int = 24,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = min(max(1, page_size), 60)

    filters = [Exercise.is_valid_exercise.is_(True)]
    if muscle:
        filters.append(Exercise.muscle == muscle)
    if gear:
        filters.append(Exercise.gear == gear)
    if modality:
        filters.append(Exercise.modality == modality)
    if coach_core is True:
        filters.append(Exercise.coach_core.is_(True))

    q_norm = (q or "").strip()
    if q_norm:
        like = f"%{q_norm}%"
        alias_ids = select(ExerciseAlias.exercise_id).where(
            ExerciseAlias.status == "published",
            or_(
                col(ExerciseAlias.alias).ilike(like),
                col(ExerciseAlias.alias).contains(q_norm),
            ),
        )
        filters.append(
            or_(
                col(Exercise.id).ilike(like),
                col(Exercise.name_zh).ilike(like),
                col(Exercise.name_en).ilike(like),
                col(Exercise.fdb_id).ilike(like),
                col(Exercise.id).in_(alias_ids),
            )
        )

    where = and_(*filters)
    total = int(session.exec(select(func.count()).select_from(Exercise).where(where)).one() or 0)

    has_thumb = case(
        (
            or_(
                and_(col(Exercise.image_start).is_not(None), Exercise.image_start != ""),
                and_(col(Exercise.image_end).is_not(None), Exercise.image_end != ""),
            ),
            1,
        ),
        else_=0,
    )
    rows = session.exec(
        select(Exercise)
        .where(where)
        .order_by(
            col(Exercise.coach_core).desc(),
            has_thumb.desc(),
            col(Exercise.name_zh),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    media_maps = _published_media_by_exercise(session, [ex.id for ex in rows])
    items = [_public_list_item(ex, media_maps.get(ex.id, {})) for ex in rows]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


def thumbs_by_ids(session: Session, exercise_ids: list[str]) -> dict[str, str | None]:
    ids = [i for i in exercise_ids if i]
    if not ids:
        return {}
    rows = session.exec(
        select(Exercise).where(col(Exercise.id).in_(ids), Exercise.is_valid_exercise.is_(True))
    ).all()
    media_maps = _published_media_by_exercise(session, [ex.id for ex in rows])
    return {ex.id: thumb_for_exercise(ex, media_maps.get(ex.id, {})) for ex in rows}


def resolve_by_names(session: Session, names: list[str]) -> dict[str, dict[str, Any]]:
    """按展示名/别名解析动作 id 与缩略图；key 为入参原名。"""
    cleaned = [n.strip() for n in names if n and str(n).strip()]
    if not cleaned:
        return {}

    from app.taxonomy import canonicalize_exercise

    # 先按 name_zh / name_en / id 精确捞
    lowered = {n: n for n in cleaned}
    canon_map = {n: canonicalize_exercise(n) for n in cleaned}

    rows = session.exec(
        select(Exercise).where(
            Exercise.is_valid_exercise.is_(True),
            or_(
                col(Exercise.name_zh).in_(cleaned),
                col(Exercise.name_en).in_(cleaned),
                col(Exercise.id).in_(cleaned),
            ),
        )
    ).all()

    by_zh = {ex.name_zh: ex for ex in rows if ex.name_zh}
    by_en = {ex.name_en: ex for ex in rows if ex.name_en}
    by_id = {ex.id: ex for ex in rows}

    # 别名命中
    alias_rows = session.exec(
        select(ExerciseAlias).where(
            ExerciseAlias.status == "published",
            col(ExerciseAlias.alias).in_(cleaned + list(canon_map.values())),
        )
    ).all()
    alias_to_id = {a.alias: a.exercise_id for a in alias_rows}
    missing_ids = [eid for eid in alias_to_id.values() if eid not in by_id]
    if missing_ids:
        extra = session.exec(
            select(Exercise).where(
                col(Exercise.id).in_(missing_ids),
                Exercise.is_valid_exercise.is_(True),
            )
        ).all()
        for ex in extra:
            by_id[ex.id] = ex
            if ex.name_zh:
                by_zh.setdefault(ex.name_zh, ex)

    matched: dict[str, Exercise] = {}
    for name in cleaned:
        ex = by_zh.get(name) or by_en.get(name) or by_id.get(name)
        if not ex:
            aid = alias_to_id.get(name) or alias_to_id.get(canon_map.get(name) or "")
            if aid:
                ex = by_id.get(aid)
        if not ex:
            # catalog 内存名 → id
            from app.exercises_catalog import EXERCISE_BY_NAME

            detail = EXERCISE_BY_NAME.get(canon_map.get(name) or "") or EXERCISE_BY_NAME.get(name)
            if detail and detail.get("id"):
                ex = session.get(Exercise, str(detail["id"]))
                if ex and not ex.is_valid_exercise:
                    ex = None
        if ex:
            matched[name] = ex

    media_maps = _published_media_by_exercise(session, [ex.id for ex in matched.values()])
    out: dict[str, dict[str, Any]] = {}
    for name, ex in matched.items():
        out[name] = {
            "id": ex.id,
            "name_zh": ex.name_zh,
            "thumb_url": thumb_for_exercise(ex, media_maps.get(ex.id, {})),
        }
    _ = lowered  # keep for clarity / future fuzzy
    return out


def get_public_exercise(session: Session, exercise_id: str) -> dict[str, Any] | None:
    ex = session.get(Exercise, exercise_id)
    if not ex or not ex.is_valid_exercise:
        return None

    media_rows = session.exec(
        select(ExerciseMedia).where(
            ExerciseMedia.exercise_id == exercise_id,
            ExerciseMedia.status == "published",
        )
    ).all()
    published = {m.role: m for m in media_rows}
    slots = []
    for role in MEDIA_ROLES:
        m = published.get(role)
        url = media_url(m.url if m else None)
        if not url and role == "start":
            url = media_url(ex.image_start)
        if not url and role == "end":
            url = media_url(ex.image_end)
        slots.append({"role": role, "url": url})

    aliases = session.exec(
        select(ExerciseAlias).where(
            ExerciseAlias.exercise_id == exercise_id,
            ExerciseAlias.status == "published",
        )
    ).all()

    return {
        "id": ex.id,
        "name_zh": ex.name_zh,
        "name_en": ex.name_en,
        "muscle": ex.muscle,
        "sub_region": ex.sub_region,
        "movement_pattern": ex.movement_pattern,
        "gear": ex.gear,
        "modality": ex.modality,
        "coach_core": bool(ex.coach_core),
        "joint_stress": ex.joint_stress or {},
        "instructions_zh": ex.instructions_zh or [],
        "cues_zh": ex.cues_zh or [],
        "common_mistakes_zh": ex.common_mistakes_zh or [],
        "aliases": [a.alias for a in aliases],
        "slots": slots,
    }
