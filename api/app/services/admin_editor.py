"""A2 admin write paths: exercise fields, media slots, AI draft."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlmodel import Session, col, select

from app.exercises_catalog import reload_all
from app.models import (
    Exercise,
    ExerciseAlias,
    ExerciseMedia,
    MediaUnmatchedPool,
    PlanExercise,
    utcnow,
)
from app.services.admin_catalog import MEDIA_ROLES, get_exercise_detail, media_url
from app.services.storage import save_public_asset

_MAX_UPLOAD_BYTES = 40 * 1024 * 1024
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_VIDEO_EXTS = {".mp4", ".webm", ".mov"}
_JOINTS = ("waist", "knee", "shoulder", "wrist", "elbow")
_LEVELS = {"low", "medium", "high"}
_MUSCLES = {"胸", "背", "肩", "腿", "臂", "核心", "全身"}
_GEARS = {"自由重量", "器械", "绳索", "自重"}
_MODALITIES = {"抗阻", "有氧", "HIIT", "灵活性"}
_PATTERNS = {
    "水平推",
    "垂直推",
    "水平拉",
    "垂直拉",
    "膝主导(蹲)",
    "髋主导(铰链)",
    "肘屈伸(弯举/臂屈伸)",
    "肩孤立(平举)",
    "核心卷曲/稳定",
    "全身心肺/综合",
    "拉伸/灵活",
}
_PATTERN_ALIASES = {
    "肩外展": "肩孤立(平举)",
    "侧平举": "肩孤立(平举)",
    "平举": "肩孤立(平举)",
    "外展": "肩孤立(平举)",
    "推胸": "水平推",
    "卧推": "水平推",
    "夹胸": "水平推",
    "飞鸟": "水平推",
    "肩推": "垂直推",
    "推举": "垂直推",
    "划船": "水平拉",
    "面拉": "水平拉",
    "下拉": "垂直拉",
    "下压": "垂直拉",  # 直臂下压 / 绳索下压：拉向，不是心肺
    "引体": "垂直拉",
    "深蹲": "膝主导(蹲)",
    "箭步": "膝主导(蹲)",
    "硬拉": "髋主导(铰链)",
    "臀桥": "髋主导(铰链)",
    "髋推": "髋主导(铰链)",
    "弯举": "肘屈伸(弯举/臂屈伸)",
    "臂屈伸": "肘屈伸(弯举/臂屈伸)",
    "肘屈伸": "肘屈伸(弯举/臂屈伸)",
    "平板支撑": "核心卷曲/稳定",
    "卷腹": "核心卷曲/稳定",
    "拉伸": "拉伸/灵活",
    "热身": "拉伸/灵活",
}


def _normalize_pattern(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if text in _PATTERNS:
        return text
    for key, mapped in _PATTERN_ALIASES.items():
        if key in text:
            return mapped
    return None


def _normalize_enum(value: str | None, allowed: set[str]) -> str | None:
    text = (value or "").strip()
    return text if text in allowed else None


_SUB_BY_MUSCLE = {
    "胸": {"上胸", "中胸", "下胸", "胸中缝/内侧", "胸部整体"},
    "背": {"背阔肌/背宽", "中上背/背厚", "下背/竖脊肌", "斜方肌"},
    "肩": {"肩前束", "肩中束", "肩后束", "肩袖/稳定", "肩部整体"},
    "腿": {"股四头肌(前侧)", "腘绳肌(后侧)", "臀部", "内收/外展肌", "小腿", "腿部整体"},
    "臂": {"肱二头肌", "肱三头肌", "前臂"},
    "核心": {"上腹/腹直肌", "下腹", "腹斜肌(侧腹)", "核心抗旋/稳定"},
    "全身": {"心肺有氧", "全身爆发/HIIT", "全身拉伸/灵活"},
}
_SUB_ALIASES = {
    "前束": "肩前束",
    "中束": "肩中束",
    "后束": "肩后束",
    "三角肌前": "肩前束",
    "三角肌中": "肩中束",
    "三角肌后": "肩后束",
    "中后束": "肩中束、肩后束",
}


def _normalize_sub_region(value: str | None, muscle: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    allowed = _SUB_BY_MUSCLE.get(muscle or "", set())
    parts = [p.strip() for p in re.split(r"[、,/，|]+", text) if p.strip()]
    mapped: list[str] = []
    for part in parts:
        if part in allowed:
            mapped.append(part)
            continue
        for key, target in _SUB_ALIASES.items():
            if key in part:
                for item in target.split("、"):
                    if item in allowed and item not in mapped:
                        mapped.append(item)
                break
    if mapped:
        return "、".join(mapped)
    if "整体" in text and muscle:
        whole = next((x for x in allowed if "整体" in x), None)
        return whole
    return None


def _safe_name(name: str) -> str:
    stem = Path(name).stem
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_") or "file"
    return clean[:48]


def _media_dict(row: ExerciseMedia | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "media_id": row.id,
        "url": media_url(row.url),
        "status": row.status,
        "source": row.source,
        "meta": row.meta or {},
    }


def enrich_detail_slots(session: Session, detail: dict[str, Any]) -> dict[str, Any]:
    """Attach draft / published / rollback hints onto detail.slots."""
    exercise_id = detail["id"]
    ex = session.get(Exercise, exercise_id)
    rows = session.exec(
        select(ExerciseMedia)
        .where(ExerciseMedia.exercise_id == exercise_id)
        .order_by(col(ExerciseMedia.created_at).desc())
    ).all()
    published = {m.role: m for m in rows if m.status == "published"}
    drafts = {m.role: m for m in rows if m.status == "draft"}
    archived = {}
    for m in rows:
        if m.status != "archived":
            continue
        archived.setdefault(m.role, m)  # newest first due to order
    slots = []
    for role in MEDIA_ROLES:
        pub = published.get(role)
        draft = drafts.get(role)
        seed_url = None
        if ex is not None:
            if role == "start":
                seed_url = media_url(ex.image_start)
            elif role == "end":
                seed_url = media_url(ex.image_end)
        active = draft or pub
        url = media_url(active.url if active else None) or seed_url
        if draft:
            status = "draft"
        elif pub:
            status = "published"
        elif seed_url:
            status = "published"
        else:
            status = "empty"
        slots.append(
            {
                "role": role,
                "url": url,
                "status": status,
                "source": (active.source if active else ("seed" if seed_url else None)),
                "media_id": active.id if active else None,
                "published": _media_dict(pub)
                or (
                    {
                        "media_id": None,
                        "url": seed_url,
                        "status": "published",
                        "source": "seed",
                        "meta": {},
                    }
                    if seed_url
                    else None
                ),
                "draft": _media_dict(draft),
                "can_rollback": bool(archived.get(role) or (pub and draft)),
                "rollback_media_id": (archived.get(role).id if archived.get(role) else None),
            }
        )
    detail["slots"] = slots
    return detail


def get_editable_detail(session: Session, exercise_id: str) -> dict[str, Any] | None:
    detail = get_exercise_detail(session, exercise_id)
    if not detail:
        return None
    return enrich_detail_slots(session, detail)


def _clean_list(values: list[Any] | None, *, limit: int = 12) -> list[str]:
    out: list[str] = []
    for item in values or []:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _clean_joint_stress(raw: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for joint in _JOINTS:
        level = str((raw or {}).get(joint, "")).strip().lower()
        if level in _LEVELS:
            out[joint] = level
    return out


def _next_exercise_id(session: Session) -> str:
    ids = session.exec(select(Exercise.id)).all()
    max_n = 0
    for raw in ids:
        text = str(raw or "").strip()
        if text.isdigit():
            max_n = max(max_n, int(text))
    return f"{max_n + 1:04d}"


def create_exercise(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    name_zh = str(payload.get("name_zh") or "").strip()
    if not name_zh:
        raise HTTPException(status_code=400, detail="中文名不能为空")

    exercise_id = str(payload.get("id") or "").strip() or _next_exercise_id(session)
    if session.get(Exercise, exercise_id):
        raise HTTPException(status_code=409, detail=f"动作 ID 已存在: {exercise_id}")

    name_en = str(payload.get("name_en") or "").strip() or name_zh
    muscle = str(payload.get("muscle") or "全身").strip() or "全身"
    gear = str(payload.get("gear") or "器械").strip() or "器械"
    modality = str(payload.get("modality") or "抗阻").strip() or "抗阻"
    sub_region = str(payload.get("sub_region") or "").strip() or None
    movement_pattern = str(payload.get("movement_pattern") or "").strip() or None
    coach_core = bool(payload.get("coach_core", False))
    aliases = _clean_list(payload.get("aliases"), limit=20)
    variant_of = str(payload.get("variant_of") or "").strip() or None
    female_variant = str(payload.get("female_variant") or "").strip() or None
    if variant_of and not session.get(Exercise, variant_of):
        raise HTTPException(status_code=400, detail=f"variant_of 指向的动作不存在: {variant_of}")
    if female_variant and not session.get(Exercise, female_variant):
        raise HTTPException(status_code=400, detail=f"female_variant 指向的动作不存在: {female_variant}")

    ex = Exercise(
        id=exercise_id,
        name_en=name_en,
        name_zh=name_zh,
        body_part=muscle,
        equipment=gear,
        category=gear,
        muscle=muscle,
        sub_region=sub_region,
        movement_pattern=movement_pattern,
        gear=gear,
        modality=modality,
        coach_core=coach_core,
        roles=["主力"] if coach_core else [],
        is_valid_exercise=True,
        needs_review=bool(payload.get("needs_review", True)),
        joint_stress=_clean_joint_stress(payload.get("joint_stress"))
        or {
            "waist": "low",
            "knee": "low",
            "shoulder": "low",
            "wrist": "low",
            "elbow": "low",
        },
        instructions_zh=_clean_list(payload.get("instructions_zh"), limit=8),
        cues_zh=_clean_list(payload.get("cues_zh"), limit=8),
        common_mistakes_zh=_clean_list(payload.get("common_mistakes_zh"), limit=8),
        variant_of=variant_of,
        female_variant=female_variant,
        text_source="admin_create",
        updated_at=utcnow(),
    )
    if "slot_roles" in payload and payload["slot_roles"] is not None:
        from app.slot_roles import normalize_slot_roles

        ex.slot_roles = normalize_slot_roles(payload["slot_roles"])
    session.add(ex)
    for alias in aliases:
        if alias == name_zh:
            continue
        session.add(
            ExerciseAlias(exercise_id=exercise_id, alias=alias, status="published")
        )
    session.commit()
    reload_all()
    detail = get_editable_detail(session, exercise_id)
    assert detail is not None
    return detail


_FEMALE_SUFFIX = "·女"


def female_display_name(base_name: str) -> str:
    name = (base_name or "").strip()
    if not name:
        return f"未命名{_FEMALE_SUFFIX}"
    if name.endswith(_FEMALE_SUFFIX):
        return name
    return f"{name}{_FEMALE_SUFFIX}"


def derive_female_variant(
    session: Session,
    source_id: str,
    *,
    copy_cues: bool = True,
) -> dict[str, Any]:
    """从男版/通用 SKU 派生女版：拷贝分类字段，双向挂 variant_of / female_variant。

    不拷贝示范媒体（女版需工坊另切片）。若男版已有 female_variant 且仍有效，直接返回已有女版。
    """
    source = session.get(Exercise, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源动作不存在")
    # 已经是女版：直接返回
    if (source.variant_of or "").strip():
        detail = get_editable_detail(session, source_id)
        assert detail is not None
        return {"exercise": detail, "created": False, "reason": "already_female"}

    existing_id = (source.female_variant or "").strip()
    if existing_id:
        existing = session.get(Exercise, existing_id)
        if existing and getattr(existing, "is_valid_exercise", True):
            # 补齐反向链接
            if (existing.variant_of or "").strip() != source_id:
                existing.variant_of = source_id
                session.add(existing)
                session.commit()
                reload_all()
            detail = get_editable_detail(session, existing_id)
            assert detail is not None
            return {"exercise": detail, "created": False, "reason": "already_linked"}

    base_name = (source.name_zh or "").strip() or source_id
    female_name = female_display_name(base_name)
    # 同名女版已存在但未挂链：复用并补链
    same_name = session.exec(
        select(Exercise).where(
            Exercise.name_zh == female_name,  # type: ignore[arg-type]
            Exercise.is_valid_exercise.is_(True),  # type: ignore[arg-type]
        )
    ).first()
    if same_name:
        same_name.variant_of = source_id
        source.female_variant = same_name.id
        session.add(same_name)
        session.add(source)
        session.commit()
        reload_all()
        detail = get_editable_detail(session, same_name.id)
        assert detail is not None
        return {"exercise": detail, "created": False, "reason": "linked_existing_name"}

    aliases = [base_name]
    for row in session.exec(
        select(ExerciseAlias).where(
            ExerciseAlias.exercise_id == source_id,
            ExerciseAlias.status == "published",
        )
    ).all():
        a = (row.alias or "").strip()
        if a and a not in aliases and a != female_name:
            aliases.append(a)

    payload: dict[str, Any] = {
        "name_zh": female_name,
        "name_en": source.name_en or female_name,
        "muscle": source.muscle or "全身",
        "sub_region": source.sub_region,
        "movement_pattern": source.movement_pattern,
        "gear": source.gear or "器械",
        "modality": source.modality or "抗阻",
        "coach_core": False,
        "needs_review": True,
        "slot_roles": list(source.slot_roles or []),
        "aliases": aliases,
        "variant_of": source_id,
        "joint_stress": source.joint_stress or {},
    }
    if copy_cues:
        payload["cues_zh"] = list(source.cues_zh or [])
        payload["common_mistakes_zh"] = list(source.common_mistakes_zh or [])
        payload["instructions_zh"] = list(source.instructions_zh or [])

    created = create_exercise(session, payload)
    female_id = str(created["id"])
    # create_exercise 已 commit；回写男版 female_variant
    source = session.get(Exercise, source_id)
    if source:
        source.female_variant = female_id
        source.updated_at = utcnow()
        session.add(source)
        session.commit()
        reload_all()
    detail = get_editable_detail(session, female_id)
    assert detail is not None
    return {"exercise": detail, "created": True, "reason": "created"}


def delete_exercise(session: Session, exercise_id: str) -> dict[str, Any]:
    """硬删动作 SKU：清别名/素材槽；计划行只解绑 id（保留动作名）；H5 打卡按名不受影响。"""
    ex = session.get(Exercise, exercise_id)
    if not ex:
        raise HTTPException(status_code=404, detail="动作不存在")
    name = ex.name_zh or exercise_id

    for row in session.exec(
        select(ExerciseMedia).where(ExerciseMedia.exercise_id == exercise_id)
    ).all():
        session.delete(row)
    for row in session.exec(
        select(ExerciseAlias).where(ExerciseAlias.exercise_id == exercise_id)
    ).all():
        session.delete(row)
    for pe in session.exec(
        select(PlanExercise).where(PlanExercise.exercise_id == exercise_id)
    ).all():
        if not (pe.exercise_name or "").strip():
            pe.exercise_name = name
        pe.exercise_id = None
        session.add(pe)
    for pool in session.exec(
        select(MediaUnmatchedPool).where(MediaUnmatchedPool.bound_exercise_id == exercise_id)
    ).all():
        pool.bound_exercise_id = None
        pool.bound_media_id = None
        if pool.status == "bound":
            pool.status = "pending"
        session.add(pool)

    session.delete(ex)
    session.commit()
    reload_all()
    return {"ok": True, "id": exercise_id, "name_zh": name}


def update_exercise(session: Session, exercise_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ex = session.get(Exercise, exercise_id)
    if not ex:
        raise HTTPException(status_code=404, detail="动作不存在")

    old_name = ex.name_zh
    if "name_zh" in payload and payload["name_zh"] is not None:
        new_name = str(payload["name_zh"]).strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="中文名不能为空")
        if new_name != old_name:
            exists = session.exec(
                select(ExerciseAlias).where(
                    ExerciseAlias.exercise_id == exercise_id,
                    ExerciseAlias.alias == old_name,
                )
            ).first()
            if not exists and old_name.strip():
                session.add(
                    ExerciseAlias(
                        exercise_id=exercise_id,
                        alias=old_name.strip(),
                        status="published",
                    )
                )
            ex.name_zh = new_name

    if "muscle" in payload and payload["muscle"] is not None:
        ex.muscle = str(payload["muscle"]).strip() or ex.muscle
    if "sub_region" in payload:
        value = payload["sub_region"]
        ex.sub_region = str(value).strip() if value else None
    if "movement_pattern" in payload:
        value = payload["movement_pattern"]
        ex.movement_pattern = str(value).strip() if value else None
    if "gear" in payload and payload["gear"] is not None:
        ex.gear = str(payload["gear"]).strip() or ex.gear
    if "modality" in payload and payload["modality"] is not None:
        ex.modality = str(payload["modality"]).strip() or ex.modality
    if "coach_core" in payload and payload["coach_core"] is not None:
        ex.coach_core = bool(payload["coach_core"])
    if "needs_review" in payload and payload["needs_review"] is not None:
        ex.needs_review = bool(payload["needs_review"])
    if "is_valid_exercise" in payload and payload["is_valid_exercise"] is not None:
        # False = 从 H5 动作库下架（仍留在后台，可再上架）
        ex.is_valid_exercise = bool(payload["is_valid_exercise"])
    if "instructions_zh" in payload and payload["instructions_zh"] is not None:
        ex.instructions_zh = _clean_list(payload["instructions_zh"], limit=8)
    if "cues_zh" in payload and payload["cues_zh"] is not None:
        ex.cues_zh = _clean_list(payload["cues_zh"], limit=8)
    if "common_mistakes_zh" in payload and payload["common_mistakes_zh"] is not None:
        ex.common_mistakes_zh = _clean_list(payload["common_mistakes_zh"], limit=8)
    if "joint_stress" in payload and payload["joint_stress"] is not None:
        ex.joint_stress = _clean_joint_stress(payload["joint_stress"])
    if "slot_roles" in payload and payload["slot_roles"] is not None:
        from app.slot_roles import normalize_slot_roles

        ex.slot_roles = normalize_slot_roles(payload["slot_roles"])
    if "variant_of" in payload:
        raw = payload["variant_of"]
        value = str(raw).strip() if raw else None
        if value and not session.get(Exercise, value):
            raise HTTPException(status_code=400, detail=f"variant_of 指向的动作不存在: {value}")
        ex.variant_of = value or None
    if "female_variant" in payload:
        raw = payload["female_variant"]
        value = str(raw).strip() if raw else None
        if value and not session.get(Exercise, value):
            raise HTTPException(status_code=400, detail=f"female_variant 指向的动作不存在: {value}")
        ex.female_variant = value or None

    if "aliases" in payload and payload["aliases"] is not None:
        wanted = _clean_list(payload["aliases"], limit=20)
        existing = session.exec(
            select(ExerciseAlias).where(ExerciseAlias.exercise_id == exercise_id)
        ).all()
        by_alias = {row.alias: row for row in existing}
        keep = set(wanted)
        for alias in wanted:
            row = by_alias.get(alias)
            if row:
                row.status = "published"
                session.add(row)
            else:
                session.add(
                    ExerciseAlias(exercise_id=exercise_id, alias=alias, status="published")
                )
        for row in existing:
            if row.alias not in keep:
                row.status = "draft"
                session.add(row)

    ex.updated_at = utcnow()
    session.add(ex)
    session.commit()
    reload_all()
    detail = get_editable_detail(session, exercise_id)
    assert detail is not None
    return detail


def _process_image_bytes(data: bytes, ext: str) -> tuple[bytes, str]:
    try:
        from io import BytesIO

        from PIL import Image
    except Exception:
        return data, ext

    img = Image.open(BytesIO(data))
    img = img.convert("RGB") if img.mode not in ("RGB", "L") else img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    if side > 1024:
        img = img.resize((1024, 1024))
    out = BytesIO()
    img.save(out, format="JPEG", quality=88, optimize=True)
    return out.getvalue(), ".jpg"


def save_media_bytes(
    session: Session,
    exercise_id: str,
    *,
    role: str,
    filename: str,
    raw: bytes,
    publish: bool = False,
    source: str = "upload",
) -> dict[str, Any]:
    """把字节写入动作槽位（draft/published），供单文件上传与批量池复用。"""
    if role not in MEDIA_ROLES:
        raise HTTPException(status_code=400, detail=f"无效槽位: {role}")
    ex = session.get(Exercise, exercise_id)
    if not ex:
        raise HTTPException(status_code=404, detail="动作不存在")

    filename = filename or "upload.bin"
    ext = Path(filename).suffix.lower()
    allowed = _IMAGE_EXTS | {".gif"}
    if role in ("highlight_video", "demo"):
        allowed = allowed | _VIDEO_EXTS
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '(无扩展名)'}")
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件过大（上限 40MB）")

    save_ext = ext or ".bin"
    payload = raw
    if ext in _IMAGE_EXTS - {".gif"}:
        payload, save_ext = _process_image_bytes(raw, ext)

    token = uuid.uuid4().hex[:10]
    out_name = f"{role}_{token}_{_safe_name(filename)}{save_ext}"
    key = f"exercises/custom/{exercise_id}/{out_name}"
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
    }.get(save_ext.lower(), "application/octet-stream")
    stored_url = save_public_asset(payload, key, mime)

    old_drafts = session.exec(
        select(ExerciseMedia).where(
            ExerciseMedia.exercise_id == exercise_id,
            ExerciseMedia.role == role,
            ExerciseMedia.status == "draft",
        )
    ).all()
    for row in old_drafts:
        row.status = "archived"
        session.add(row)

    status = "published" if publish else "draft"
    if publish:
        pubs = session.exec(
            select(ExerciseMedia).where(
                ExerciseMedia.exercise_id == exercise_id,
                ExerciseMedia.role == role,
                ExerciseMedia.status == "published",
            )
        ).all()
        for row in pubs:
            row.status = "archived"
            session.add(row)
        if role == "start":
            ex.image_start = stored_url
        if role == "end":
            ex.image_end = stored_url

    media = ExerciseMedia(
        exercise_id=exercise_id,
        role=role,
        url=stored_url,
        status=status,
        source=source,
        meta={"original_name": filename, "bytes": len(payload)},
    )
    ex.updated_at = utcnow()
    session.add(media)
    session.add(ex)
    session.commit()
    session.refresh(media)
    if publish:
        reload_all()
    detail = get_editable_detail(session, exercise_id)
    assert detail is not None
    return detail


async def upload_media(
    session: Session,
    exercise_id: str,
    *,
    role: str,
    file: UploadFile,
    publish: bool = False,
) -> dict[str, Any]:
    filename = file.filename or "upload.bin"
    raw = await file.read()
    return save_media_bytes(
        session,
        exercise_id,
        role=role,
        filename=filename,
        raw=raw,
        publish=publish,
        source="upload",
    )


def publish_media(session: Session, media_id: int) -> dict[str, Any]:
    media = session.get(ExerciseMedia, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="素材不存在")
    if media.status not in {"draft", "archived"}:
        raise HTTPException(status_code=400, detail="仅 draft/archived 可发布")

    pubs = session.exec(
        select(ExerciseMedia).where(
            ExerciseMedia.exercise_id == media.exercise_id,
            ExerciseMedia.role == media.role,
            ExerciseMedia.status == "published",
            ExerciseMedia.id != media.id,
        )
    ).all()
    for row in pubs:
        row.status = "archived"
        session.add(row)

    # clear other drafts for same role
    drafts = session.exec(
        select(ExerciseMedia).where(
            ExerciseMedia.exercise_id == media.exercise_id,
            ExerciseMedia.role == media.role,
            ExerciseMedia.status == "draft",
            ExerciseMedia.id != media.id,
        )
    ).all()
    for row in drafts:
        row.status = "archived"
        session.add(row)

    media.status = "published"
    session.add(media)
    ex = session.get(Exercise, media.exercise_id)
    if ex:
        if media.role == "start":
            ex.image_start = media.url
        if media.role == "end":
            ex.image_end = media.url
        ex.updated_at = utcnow()
        session.add(ex)
    session.commit()
    reload_all()
    detail = get_editable_detail(session, media.exercise_id)
    assert detail is not None
    return detail


def rollback_media(session: Session, media_id: int) -> dict[str, Any]:
    """Re-publish an archived media row (or the previous published behind a draft)."""
    media = session.get(ExerciseMedia, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="素材不存在")
    if media.status == "published":
        # rollback means restore newest archived for this role
        prev = session.exec(
            select(ExerciseMedia)
            .where(
                ExerciseMedia.exercise_id == media.exercise_id,
                ExerciseMedia.role == media.role,
                ExerciseMedia.status == "archived",
            )
            .order_by(col(ExerciseMedia.created_at).desc())
        ).first()
        if not prev:
            raise HTTPException(status_code=400, detail="没有可回滚的历史版本")
        return publish_media(session, prev.id)
    if media.status == "draft":
        # discard draft by archiving; keep current published
        media.status = "archived"
        session.add(media)
        ex = session.get(Exercise, media.exercise_id)
        if ex:
            ex.updated_at = utcnow()
            session.add(ex)
        session.commit()
        detail = get_editable_detail(session, media.exercise_id)
        assert detail is not None
        return detail
    return publish_media(session, media.id)


def clear_slot(session: Session, exercise_id: str, role: str) -> dict[str, Any]:
    """Archive published/draft for a role and clear seed path so the slot becomes empty.

    删「动图」时：若起始封面也是工坊切片带出来的（source=video_studio），一并归档，
    避免 H5 只剩一张静图还以为示范还在。
    """
    if role not in MEDIA_ROLES:
        raise HTTPException(status_code=400, detail=f"无效槽位: {role}")
    ex = session.get(Exercise, exercise_id)
    if not ex:
        raise HTTPException(status_code=404, detail="动作不存在")

    def _active_rows(r: str) -> list[ExerciseMedia]:
        return list(
            session.exec(
                select(ExerciseMedia).where(
                    ExerciseMedia.exercise_id == exercise_id,
                    ExerciseMedia.role == r,
                    col(ExerciseMedia.status).in_(["published", "draft"]),
                )
            ).all()
        )

    rows = _active_rows(role)
    seed_only = (role == "start" and ex.image_start) or (role == "end" and ex.image_end)
    if not rows and not seed_only:
        raise HTTPException(status_code=400, detail="该槽位已是空的")

    for row in rows:
        row.status = "archived"
        session.add(row)

    if role == "start":
        ex.image_start = None
    if role == "end":
        ex.image_end = None

    # 工坊「做成示范」会同时写 demo + start；删动图时带走同源封面
    if role == "demo":
        studio_starts = [r for r in _active_rows("start") if (r.source or "") == "video_studio"]
        for row in studio_starts:
            row.status = "archived"
            session.add(row)
        if studio_starts and ex.image_start in {r.url for r in studio_starts}:
            ex.image_start = None

    ex.updated_at = utcnow()
    session.add(ex)
    session.commit()
    reload_all()
    detail = get_editable_detail(session, exercise_id)
    assert detail is not None
    return detail


def _guess_taxonomy(ex: Exercise) -> dict[str, Any]:
    """后台一次性「猜分类」：用动作名启发，产出可写入的字段建议。

    注意：这里是唯一允许靠名字猜的地方。配课/换动作热路径禁止抄这套名单；
    猜完后人工确认写入 muscle / movement_pattern / slot_roles / sub_region。
    """
    blob = f"{ex.name_zh or ''} {ex.name_en or ''}".lower()
    muscle = (ex.muscle or "").strip() or None
    sub = (ex.sub_region or "").strip() or None
    pattern = (ex.movement_pattern or "").strip() or None
    gear = (ex.gear or "").strip() or None
    modality = (ex.modality or "").strip() or "抗阻"
    note_bits: list[str] = []

    if any(k in blob for k in ("侧平举", "侧平", "lateral raise", "y字", "y-raise", "y raise")):
        muscle = muscle or "肩"
        if not sub:
            sub = "肩中束、肩后束" if ("y" in blob or "y字" in blob) else "肩中束"
            note_bits.append("侧平举类主练中束；Y 字轨迹通常兼后束，已建议多选，请核对")
        pattern = pattern or "肩孤立(平举)"
        gear = gear or ("绳索" if "绳" in blob or "cable" in blob else "自由重量")
    elif any(k in blob for k in ("飞鸟", "fly", "飞鸟")):
        muscle = muscle or "胸"
        sub = sub or "胸部整体"
        pattern = pattern or "水平推"
    elif any(k in blob for k in ("划船", "row", "面拉")):
        muscle = muscle or "背"
        sub = sub or "中上背/背厚"
        pattern = pattern or "水平拉"
    elif any(k in blob for k in ("下拉", "下压", "pulldown", "pushdown", "引体")):
        # 直臂下压 / 高位下拉 / 绳索下压 → 垂直拉；不是心肺
        muscle = muscle or ("臂" if ("三头" in blob or "pushdown" in blob) else "背")
        if not sub:
            sub = "肱三头肌" if muscle == "臂" else "中上背/背厚"
        pattern = pattern or "垂直拉"
    elif any(k in blob for k in ("推举", "press", "肩推")):
        muscle = muscle or "肩"
        sub = sub or "肩前束"
        pattern = pattern or "垂直推"
    elif any(k in blob for k in ("深蹲", "squat", "箭步")):
        muscle = muscle or "腿"
        sub = sub or "股四头肌(前侧)"
        pattern = pattern or "膝主导(蹲)"
    elif any(k in blob for k in ("硬拉", "deadlift", "臀桥", "髋推")):
        muscle = muscle or "腿"
        sub = sub or "腘绳肌(后侧)"
        pattern = pattern or "髋主导(铰链)"

    if not muscle:
        muscle = "全身"
        note_bits.append("未能从名称判断部位，请人工选择")
    if not sub:
        whole = {
            "胸": "胸部整体",
            "背": "中上背/背厚",
            "肩": "肩部整体",
            "腿": "腿部整体",
            "臂": "肱二头肌",
            "核心": "核心抗旋/稳定",
            "全身": "全身爆发/HIIT",
        }.get(muscle or "", "")
        if whole:
            sub = whole
            note_bits.append("靶区不确定时先填「整体」，确认后可改成具体束")
    # 猜不出模式就留空，禁止用「全身心肺/综合」凑数（抗阻动作会被标错）
    if not pattern:
        mapped = None
        for key, val in _PATTERN_ALIASES.items():
            if key.lower() in blob:
                mapped = val
                break
        if mapped:
            pattern = mapped
        else:
            note_bits.append("动作模式不确定，请人工选择，勿用心肺凑数")
    if not gear:
        gear = "自由重量"

    shoulder_hit = any(k in blob for k in ("肩", "平举", "推举", "飞鸟", "raise", "press", "fly"))
    joint = {
        "waist": "medium" if any(k in blob for k in ("硬拉", "深蹲", "deadlift", "squat")) else "low",
        "knee": "medium" if any(k in blob for k in ("深蹲", "弓步", "squat", "lunge")) else "low",
        "shoulder": "medium" if shoulder_hit else "low",
        "wrist": "low",
        "elbow": "low",
    }

    return {
        "muscle": muscle,
        "sub_region": sub,
        "movement_pattern": pattern,
        "gear": gear,
        "modality": modality,
        "joint_stress": joint,
        "needs_review": True,
        "confidence_note": "；".join(note_bits) if note_bits else None,
    }


async def ai_draft(session: Session, exercise_id: str) -> dict[str, Any]:
    ex = session.get(Exercise, exercise_id)
    if not ex:
        raise HTTPException(status_code=404, detail="动作不存在")

    from app.brain.llm import TEMPERATURE_STRUCTURED, get_llm

    pattern_opts = " / ".join(sorted(_PATTERNS))
    system = (
        "【ADMIN_EXERCISE_DRAFT】你是健身房内容运营编辑。"
        "根据动作信息生成中文教案与分类建议，只返回 JSON："
        '{"aliases": string[], "instructions_zh": string[4], '
        '"cues_zh": string[2], "common_mistakes_zh": string[2], '
        '"joint_stress": {"waist":"low|medium|high","knee":"...","shoulder":"...","wrist":"...","elbow":"..."}, '
        '"muscle": "胸|背|肩|腿|臂|核心|全身", '
        '"sub_region": "可用顿号多选，如肩中束、肩后束；不确定用××整体", '
        f'"movement_pattern": "必须是枚举之一或空字符串：{pattern_opts}", '
        '"gear": "自由重量|器械|绳索|自重", '
        '"modality": "抗阻|有氧|HIIT|灵活性", '
        '"needs_review": boolean, "confidence_note": string}'
        "规则：直臂下压/高位下拉/绳索下压=垂直拉+抗阻，绝不是全身心肺/综合；"
        "不确定的 movement_pattern 必须返回空字符串并 needs_review=true，禁止用心肺凑数。"
    )
    user = (
        f"id={ex.id}\nname_zh={ex.name_zh}\nname_en={ex.name_en}\n"
        f"muscle={ex.muscle}\nsub_region={ex.sub_region}\n"
        f"movement_pattern={ex.movement_pattern}\ngear={ex.gear}\nmodality={ex.modality}\n"
        f"existing_instructions={ex.instructions_zh}\nexisting_cues={ex.cues_zh}\n"
        f"existing_mistakes={ex.common_mistakes_zh}\n"
        "要求：分类字段可补全空白；靶区可多选；模式不确定就留空+needs_review，不要填全身心肺/综合。"
    )
    llm = get_llm()
    guess = _guess_taxonomy(ex)
    try:
        raw = await llm.complete_json(system, user, temperature=TEMPERATURE_STRUCTURED)
    except Exception as exc:  # noqa: BLE001
        raw = {}
        _ = exc

    if not isinstance(raw, dict) or "instructions_zh" not in raw:
        raw = {
            "aliases": [ex.name_zh, ex.name_en][:3],
            "instructions_zh": (ex.instructions_zh or [])[:4]
            or [
                f"准备好{guess.get('gear') or ex.gear or '器械'}，站位稳定，核心收紧。",
                f"按{guess.get('movement_pattern') or '标准动作模式'}进入起始姿势。",
                "控制节奏完成动作幅度，保持呼吸均匀。",
                "回到起始位，检查关节位置后重复。",
            ],
            "cues_zh": (ex.cues_zh or [])[:2] or ["核心绷住", "动作末端不要借力晃"],
            "common_mistakes_zh": (ex.common_mistakes_zh or [])[:2]
            or ["借力甩动", "关节超伸或塌陷"],
            "joint_stress": ex.joint_stress or guess.get("joint_stress"),
            **{k: guess[k] for k in ("muscle", "sub_region", "movement_pattern", "gear", "modality", "needs_review", "confidence_note")},
        }

    # 空分类用启发式兜底；枚举做归一，避免 AI 自由词塞进下拉
    for key in ("muscle", "sub_region", "movement_pattern", "gear", "modality"):
        if not str(raw.get(key) or "").strip():
            raw[key] = guess.get(key)

    muscle = _normalize_enum(str(raw.get("muscle") or ""), _MUSCLES) or guess.get("muscle")
    gear = _normalize_enum(str(raw.get("gear") or ""), _GEARS) or guess.get("gear")
    modality = _normalize_enum(str(raw.get("modality") or ""), _MODALITIES) or guess.get("modality")
    pattern = _normalize_pattern(str(raw.get("movement_pattern") or "")) or guess.get("movement_pattern")
    sub = _normalize_sub_region(str(raw.get("sub_region") or ""), muscle) or guess.get("sub_region")

    # 抗阻名被标成「全身心肺/综合」：用别名救一次；仍不确定则清空，逼人工选
    name_blob = f"{ex.name_zh or ''} {ex.name_en or ''}".lower()
    if pattern == "全身心肺/综合":
        rescued = None
        for key, val in _PATTERN_ALIASES.items():
            if key.lower() in name_blob:
                rescued = val
                break
        if rescued and rescued != "全身心肺/综合":
            pattern = rescued
        elif (modality or "抗阻") == "抗阻":
            pattern = None
            raw["needs_review"] = True
            note = str(raw.get("confidence_note") or "").strip()
            tip = "动作模式曾被标成心肺，已清空请人工选"
            raw["confidence_note"] = f"{note}；{tip}" if note else tip

    if raw.get("needs_review") is None:
        raw["needs_review"] = bool(guess.get("needs_review")) or not pattern
    if not str(raw.get("confidence_note") or "").strip():
        raw["confidence_note"] = guess.get("confidence_note")

    filled = ["aliases", "instructions_zh", "cues_zh", "common_mistakes_zh", "joint_stress"]
    for key, value in (
        ("muscle", muscle),
        ("sub_region", sub),
        ("movement_pattern", pattern),
        ("gear", gear),
        ("modality", modality),
    ):
        if value:
            filled.append(key)

    return {
        "id": ex.id,
        "aliases": _clean_list(raw.get("aliases"), limit=8),
        "instructions_zh": _clean_list(raw.get("instructions_zh"), limit=4),
        "cues_zh": _clean_list(raw.get("cues_zh"), limit=4),
        "common_mistakes_zh": _clean_list(raw.get("common_mistakes_zh"), limit=4),
        "joint_stress": _clean_joint_stress(raw.get("joint_stress") or guess.get("joint_stress")),
        "muscle": muscle,
        "sub_region": sub,
        "movement_pattern": pattern,
        "gear": gear,
        "modality": modality,
        "needs_review": bool(raw.get("needs_review")),
        "confidence_note": str(raw.get("confidence_note") or "").strip() or None,
        "filled_fields": filled,
    }
