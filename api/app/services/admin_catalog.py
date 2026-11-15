"""Admin catalog queries for A1 read-only browsing."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import and_, or_
from sqlmodel import Session, col, func, select

from app.models import Exercise, ExerciseAlias, ExerciseMedia

MUSCLES = ("胸", "背", "肩", "腿", "臂", "核心", "全身")
MEDIA_ROLES = ("start", "end", "demo", "highlight_video", "tip")
MediaState = Literal["none", "frames_only", "has_dynamic", "complete"]


def media_url(path: str | None) -> str | None:
    if not path:
        return None
    p = path.replace("\\", "/").lstrip("/")
    if p.startswith("http://") or p.startswith("https://") or p.startswith("/static/"):
        return p
    return f"/static/exercises/{p}"


def _published_media_by_exercise(
    session: Session, exercise_ids: list[str]
) -> dict[str, dict[str, ExerciseMedia]]:
    if not exercise_ids:
        return {}
    rows = session.exec(
        select(ExerciseMedia).where(
            col(ExerciseMedia.exercise_id).in_(exercise_ids),
            ExerciseMedia.status == "published",
        )
    ).all()
    out: dict[str, dict[str, ExerciseMedia]] = {}
    for row in rows:
        out.setdefault(row.exercise_id, {})[row.role] = row
    return out


def _aliases_by_exercise(session: Session, exercise_ids: list[str]) -> dict[str, list[str]]:
    if not exercise_ids:
        return {}
    rows = session.exec(
        select(ExerciseAlias).where(
            col(ExerciseAlias.exercise_id).in_(exercise_ids),
            ExerciseAlias.status == "published",
        )
    ).all()
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row.exercise_id, []).append(row.alias)
    return out


def _slot_flags(media_map: dict[str, ExerciseMedia]) -> dict[str, bool]:
    return {role: role in media_map for role in MEDIA_ROLES}


def _media_state(flags: dict[str, bool]) -> str:
    has_frame = flags.get("start") or flags.get("end")
    has_dynamic = flags.get("demo") or flags.get("highlight_video") or flags.get("tip")
    if flags.get("start") and flags.get("end") and flags.get("demo") and flags.get("highlight_video") and flags.get("tip"):
        return "complete"
    if has_dynamic:
        return "has_dynamic"
    if has_frame:
        return "frames_only"
    # also treat image_start path-only as frames via caller
    return "none"


def _top_risk(joint_stress: dict[str, Any] | None) -> dict[str, str] | None:
    if not joint_stress:
        return None
    rank = {"high": 3, "medium": 2, "low": 1}
    best_joint = None
    best_level = None
    best_score = 0
    for joint, level in joint_stress.items():
        score = rank.get(str(level), 0)
        if score > best_score:
            best_score = score
            best_joint = str(joint)
            best_level = str(level)
    if not best_joint:
        return None
    label = {
        "waist": "腰",
        "knee": "膝",
        "shoulder": "肩",
        "wrist": "腕",
        "elbow": "肘",
    }.get(best_joint, best_joint)
    level_zh = {"low": "低", "medium": "中", "high": "高"}.get(best_level or "", best_level or "")
    return {"joint": best_joint, "joint_zh": label, "level": best_level or "", "label": f"{label} {level_zh}"}


def exercise_list_item(
    ex: Exercise,
    *,
    aliases: list[str],
    media_map: dict[str, ExerciseMedia],
) -> dict[str, Any]:
    # Prefer start/end frames, then demo/tip stills for list thumbnails
    thumb = None
    for role in ("start", "end", "demo", "tip", "highlight_video"):
        row = media_map.get(role)
        if row and row.url:
            thumb = media_url(row.url)
            break
    if not thumb:
        thumb = media_url(ex.image_start) or media_url(ex.image_end)
    flags = _slot_flags(media_map)
    if not flags["start"] and ex.image_start:
        flags["start"] = True
    if not flags["end"] and ex.image_end:
        flags["end"] = True
    state = _media_state(flags)
    enriched = bool(ex.coach_core and (ex.cues_zh or (ex.instructions_zh and len(ex.instructions_zh) >= 4)))
    return {
        "id": ex.id,
        "name_zh": ex.name_zh,
        "name_en": ex.name_en,
        "fdb_id": ex.fdb_id,
        "muscle": ex.muscle,
        "sub_region": ex.sub_region,
        "movement_pattern": ex.movement_pattern,
        "gear": ex.gear,
        "modality": ex.modality,
        "coach_core": ex.coach_core,
        "needs_review": bool(ex.needs_review),
        "is_valid_exercise": bool(ex.is_valid_exercise),
        "aliases": aliases[:6],
        "thumb_url": thumb,
        "slots": flags,
        "media_state": state,
        "risk": _top_risk(ex.joint_stress if isinstance(ex.joint_stress, dict) else None),
        "enriched": enriched,
        "updated_at": ex.updated_at.isoformat() if ex.updated_at else None,
    }


def build_overview(session: Session) -> dict[str, Any]:
    total = int(session.exec(select(func.count()).select_from(Exercise)).one() or 0)
    coach_core = int(
        session.exec(select(func.count()).select_from(Exercise).where(Exercise.coach_core.is_(True))).one()
        or 0
    )
    needs_review = int(
        session.exec(select(func.count()).select_from(Exercise).where(Exercise.needs_review.is_(True))).one()
        or 0
    )
    with_start = int(
        session.exec(
            select(func.count())
            .select_from(Exercise)
            .where(col(Exercise.image_start).is_not(None), Exercise.image_start != "")
        ).one()
        or 0
    )
    # 主力精洗：coach_core 且 cues 非空（JSON 字段在 Python 侧统计，避免 jsonb 比较问题）
    core_rows = session.exec(select(Exercise).where(Exercise.coach_core.is_(True))).all()
    enriched_core = sum(1 for ex in core_rows if ex.cues_zh)

    media_with_any = session.exec(
        select(ExerciseMedia.exercise_id)
        .where(ExerciseMedia.status == "published")
        .distinct()
    ).all()
    # coverage matrix: among coach_core (or all if no core)
    scope = core_rows if core_rows else session.exec(select(Exercise).limit(500)).all()
    scope_ids = [ex.id for ex in scope]
    media_maps = _published_media_by_exercise(session, scope_ids)
    coverage: list[dict[str, Any]] = []
    for muscle in MUSCLES:
        group = [ex for ex in scope if ex.muscle == muscle]
        n = len(group) or 1
        row: dict[str, Any] = {"muscle": muscle, "count": len(group), "slots": {}}
        for role in MEDIA_ROLES:
            hit = 0
            for ex in group:
                flags = _slot_flags(media_maps.get(ex.id, {}))
                if role == "start" and not flags["start"] and ex.image_start:
                    flags["start"] = True
                if role == "end" and not flags["end"] and ex.image_end:
                    flags["end"] = True
                if flags.get(role):
                    hit += 1
            row["slots"][role] = round(100.0 * hit / n, 1) if group else 0.0
        coverage.append(row)

    recent = session.exec(
        select(Exercise).order_by(col(Exercise.updated_at).desc()).limit(8)
    ).all()
    recent_ids = [ex.id for ex in recent]
    recent_media = _published_media_by_exercise(session, recent_ids)
    recent_aliases = _aliases_by_exercise(session, recent_ids)

    enrich_rate = round(100.0 * enriched_core / coach_core, 1) if coach_core else 0.0
    media_rate = round(100.0 * with_start / total, 1) if total else 0.0

    return {
        "totals": {
            "exercises": total,
            "coach_core": coach_core,
            "with_media_rate": media_rate,
            "with_image_start": with_start,
            "enrich_rate": enrich_rate,
            "enriched_core": enriched_core,
            "needs_review": needs_review,
            "media_exercise_count": len(media_with_any),
        },
        "coverage": coverage,
        "recent": [
            exercise_list_item(
                ex,
                aliases=recent_aliases.get(ex.id, []),
                media_map=recent_media.get(ex.id, {}),
            )
            for ex in recent
        ],
    }


def list_exercises(
    session: Session,
    *,
    q: str | None = None,
    muscle: str | None = None,
    sub_region: str | None = None,
    gear: str | None = None,
    movement_pattern: str | None = None,
    coach_core: bool | None = None,
    media_state: str | None = None,
    needs_review: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    stmt = select(Exercise)
    filters = []
    if muscle:
        filters.append(Exercise.muscle == muscle)
    if sub_region:
        # 支持多靶区入库（「肩中束、肩后束」），筛选用包含匹配
        filters.append(col(Exercise.sub_region).contains(sub_region))
    if gear:
        filters.append(Exercise.gear == gear)
    if movement_pattern:
        filters.append(Exercise.movement_pattern == movement_pattern)
    if coach_core is not None:
        filters.append(Exercise.coach_core.is_(coach_core))
    if needs_review is not None:
        filters.append(Exercise.needs_review.is_(needs_review))

    q_norm = (q or "").strip()
    if q_norm:
        like = f"%{q_norm}%"
        alias_ids = select(ExerciseAlias.exercise_id).where(
            or_(
                col(ExerciseAlias.alias).ilike(like),
                col(ExerciseAlias.alias).contains(q_norm),
            )
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

    if filters:
        stmt = stmt.where(and_(*filters))

    # media_state needs post-filter or subquery; for A1 load matching ids then filter in Python if media_state set
    # For performance without media_state: pure SQL pagination
    if not media_state:
        count_stmt = select(func.count()).select_from(Exercise)
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        total = int(session.exec(count_stmt).one() or 0)
        rows = session.exec(
            stmt.order_by(col(Exercise.coach_core).desc(), col(Exercise.name_zh))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    else:
        rows_all = session.exec(
            stmt.order_by(col(Exercise.coach_core).desc(), col(Exercise.name_zh))
        ).all()
        ids = [ex.id for ex in rows_all]
        media_maps = _published_media_by_exercise(session, ids)
        filtered: list[Exercise] = []
        for ex in rows_all:
            flags = _slot_flags(media_maps.get(ex.id, {}))
            if not flags["start"] and ex.image_start:
                flags["start"] = True
            if not flags["end"] and ex.image_end:
                flags["end"] = True
            if _media_state(flags) == media_state:
                filtered.append(ex)
        total = len(filtered)
        start = (page - 1) * page_size
        rows = filtered[start : start + page_size]
        media_maps = _published_media_by_exercise(session, [ex.id for ex in rows])
        aliases = _aliases_by_exercise(session, [ex.id for ex in rows])
        items = [
            exercise_list_item(ex, aliases=aliases.get(ex.id, []), media_map=media_maps.get(ex.id, {}))
            for ex in rows
        ]
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    ids = [ex.id for ex in rows]
    media_maps = _published_media_by_exercise(session, ids)
    aliases = _aliases_by_exercise(session, ids)
    items = [
        exercise_list_item(ex, aliases=aliases.get(ex.id, []), media_map=media_maps.get(ex.id, {}))
        for ex in rows
    ]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


def get_exercise_detail(session: Session, exercise_id: str) -> dict[str, Any] | None:
    ex = session.get(Exercise, exercise_id)
    if not ex:
        return None
    media_rows = session.exec(
        select(ExerciseMedia)
        .where(ExerciseMedia.exercise_id == exercise_id)
        .order_by(col(ExerciseMedia.created_at).desc())
    ).all()
    aliases = session.exec(
        select(ExerciseAlias).where(
            ExerciseAlias.exercise_id == exercise_id,
            ExerciseAlias.status == "published",
        )
    ).all()
    published = {m.role: m for m in media_rows if m.status == "published"}
    slots = []
    for role in MEDIA_ROLES:
        m = published.get(role)
        url = media_url(m.url if m else None)
        if not url and role == "start":
            url = media_url(ex.image_start)
        if not url and role == "end":
            url = media_url(ex.image_end)
        slots.append(
            {
                "role": role,
                "url": url,
                "status": m.status if m else ("published" if url else "empty"),
                "source": m.source if m else ("seed" if url else None),
                "media_id": m.id if m else None,
            }
        )
    return {
        "id": ex.id,
        "name_zh": ex.name_zh,
        "name_en": ex.name_en,
        "fdb_id": ex.fdb_id,
        "muscle": ex.muscle,
        "sub_region": ex.sub_region,
        "movement_pattern": ex.movement_pattern,
        "gear": ex.gear,
        "modality": ex.modality,
        "roles": ex.roles or [],
        "coach_core": ex.coach_core,
        "needs_review": bool(ex.needs_review),
        "is_valid_exercise": bool(ex.is_valid_exercise),
        "joint_stress": ex.joint_stress or {},
        "instructions_zh": ex.instructions_zh or [],
        "cues_zh": ex.cues_zh or [],
        "common_mistakes_zh": ex.common_mistakes_zh or [],
        "description_zh": ex.description_zh,
        "aliases": [a.alias for a in aliases],
        "slots": slots,
        "updated_at": ex.updated_at.isoformat() if ex.updated_at else None,
    }


def set_review_flag(session: Session, exercise_id: str, needs_review: bool) -> dict[str, Any] | None:
    ex = session.get(Exercise, exercise_id)
    if not ex:
        return None
    ex.needs_review = needs_review
    from app.models import utcnow

    ex.updated_at = utcnow()
    session.add(ex)
    session.commit()
    session.refresh(ex)
    return {"id": ex.id, "needs_review": bool(ex.needs_review)}
