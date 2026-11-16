"""后台：计划模板 CRUD、板块/动作行编排、横向封面上传。"""

from __future__ import annotations

import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlmodel import Session, col, func, select

from app.models import (
    PLAN_GEAR_TAGS,
    PLAN_SLOT_ROLES,
    Exercise,
    PlanBlock,
    PlanExercise,
    PlanTemplate,
    utcnow,
)
_STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"
_PLANS_ROOT = _STATIC_ROOT / "plans"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_MAX_UPLOAD_BYTES = 12 * 1024 * 1024
_SLUG_RE = re.compile(r"[^a-z0-9\-]+")

LEVELS = ("beginner", "intermediate", "advanced")
TEMPLATE_TYPES = ("framework", "fixed")
LOCK_LEVELS = ("fixed", "slot")


def _slugify(raw: str) -> str:
    text = (raw or "").strip().lower().replace(" ", "-").replace("_", "-")
    # 中文标题兜底：用短 uuid
    ascii_part = _SLUG_RE.sub("-", text).strip("-")
    if not ascii_part or ascii_part == "-":
        return f"plan-{uuid.uuid4().hex[:10]}"
    return ascii_part[:32]


def _minutes_label(mn: int | None, mx: int | None) -> str | None:
    if mn is None and mx is None:
        return None
    if mn is not None and mx is not None:
        return f"{mn} 分钟" if mn == mx else f"{mn}-{mx} 分钟"
    return f"{mn or mx} 分钟"


def _clean_str_list(raw: Any, *, allowed: tuple[str, ...] | None = None, limit: int = 20) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        text = str(item or "").strip()
        if not text:
            continue
        if allowed is not None and text not in allowed:
            continue
        if text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _exercise_thumb(session: Session, exercise_id: str | None) -> str | None:
    if not exercise_id:
        return None
    sku = session.get(Exercise, exercise_id)
    if not sku or not sku.image_start:
        return None
    path = sku.image_start
    return path if path.startswith("/static/") else f"/static/exercises/{path}"


def _plan_out(session: Session, tpl: PlanTemplate, *, with_blocks: bool = False) -> dict[str, Any]:
    block_count = session.exec(
        select(func.count()).select_from(PlanBlock).where(PlanBlock.template_id == tpl.id)
    ).one()
    data: dict[str, Any] = {
        "id": tpl.id,
        "title": tpl.title,
        "subtitle": tpl.subtitle,
        "author": tpl.author,
        "badge_label": tpl.badge_label,
        "template_type": tpl.template_type,
        "level": tpl.level,
        "days_per_week": tpl.days_per_week,
        "minutes_min": tpl.minutes_min,
        "minutes_max": tpl.minutes_max,
        "minutes_label": _minutes_label(tpl.minutes_min, tpl.minutes_max),
        "muscle_tags": list(tpl.muscle_tags or []),
        "split_summary": tpl.split_summary,
        "gear_tags": list(tpl.gear_tags or []),
        "description": tpl.description,
        "cover_url": tpl.cover_url,
        "is_published": bool(tpl.is_published),
        "sort_order": tpl.sort_order,
        "block_count": int(block_count or 0),
        "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
        "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
    }
    if with_blocks:
        data["blocks"] = [
            _block_out(session, b)
            for b in session.exec(
                select(PlanBlock)
                .where(PlanBlock.template_id == tpl.id)
                .order_by(col(PlanBlock.order_index), col(PlanBlock.id))
            ).all()
        ]
    return data


def _block_out(session: Session, block: PlanBlock) -> dict[str, Any]:
    exercises = session.exec(
        select(PlanExercise)
        .where(PlanExercise.block_id == block.id)
        .order_by(col(PlanExercise.order_index), col(PlanExercise.id))
    ).all()
    return {
        "id": block.id,
        "template_id": block.template_id,
        "order_index": block.order_index,
        "title": block.title,
        "muscles": list(block.muscles or []),
        "minutes_min": block.minutes_min,
        "minutes_max": block.minutes_max,
        "minutes_label": _minutes_label(block.minutes_min, block.minutes_max),
        "cover_url": block.cover_url,
        "note": block.note,
        "exercises": [_exercise_out(session, row) for row in exercises],
    }


def _exercise_out(session: Session, row: PlanExercise) -> dict[str, Any]:
    return {
        "id": row.id,
        "block_id": row.block_id,
        "order_index": row.order_index,
        "exercise_id": row.exercise_id,
        "exercise_name": row.exercise_name,
        "role": row.role,
        "lock_level": row.lock_level,
        "target_sets": row.target_sets,
        "target_reps": row.target_reps,
        "warmup_sets": row.warmup_sets or 0,
        "alternatives": list(row.alternatives or []),
        "note": row.note,
        "thumb_url": _exercise_thumb(session, row.exercise_id),
        "pending": not (row.exercise_id or row.exercise_name),
    }


def list_admin_plans(
    session: Session,
    *,
    q: str | None = None,
    template_type: str | None = None,
    published: bool | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    filters = []
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            (col(PlanTemplate.title).like(like))
            | (col(PlanTemplate.id).like(like))
            | (col(PlanTemplate.author).like(like))
        )
    if template_type in TEMPLATE_TYPES:
        filters.append(PlanTemplate.template_type == template_type)
    if published is not None:
        filters.append(PlanTemplate.is_published == published)

    count_stmt = select(func.count()).select_from(PlanTemplate)
    stmt = select(PlanTemplate)
    for f in filters:
        count_stmt = count_stmt.where(f)
        stmt = stmt.where(f)

    total = session.exec(count_stmt).one()
    rows = session.exec(
        stmt.order_by(col(PlanTemplate.sort_order), col(PlanTemplate.id))
        .offset(max(0, (page - 1) * page_size))
        .limit(page_size)
    ).all()
    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "items": [_plan_out(session, tpl) for tpl in rows],
    }


def get_admin_plan(session: Session, plan_id: str) -> dict[str, Any]:
    tpl = session.get(PlanTemplate, plan_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="计划不存在")
    return _plan_out(session, tpl, with_blocks=True)


def create_admin_plan(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    plan_id = str(payload.get("id") or "").strip() or _slugify(title)
    plan_id = plan_id[:32]
    if session.get(PlanTemplate, plan_id):
        raise HTTPException(status_code=409, detail=f"计划 ID 已存在: {plan_id}")

    template_type = str(payload.get("template_type") or "framework").strip()
    if template_type not in TEMPLATE_TYPES:
        raise HTTPException(status_code=400, detail="template_type 只能是 framework 或 fixed")
    level = payload.get("level")
    level_s = str(level).strip() if level else None
    if level_s and level_s not in LEVELS:
        raise HTTPException(status_code=400, detail="level 无效")

    now = utcnow()
    tpl = PlanTemplate(
        id=plan_id,
        title=title,
        subtitle=_opt_str(payload.get("subtitle"), 160),
        author=_opt_str(payload.get("author"), 80),
        badge_label=_opt_str(payload.get("badge_label"), 40),
        template_type=template_type,
        level=level_s,
        days_per_week=int(payload.get("days_per_week") or 3),
        minutes_min=_opt_int(payload.get("minutes_min")),
        minutes_max=_opt_int(payload.get("minutes_max")),
        muscle_tags=_clean_str_list(payload.get("muscle_tags")),
        split_summary=_opt_str(payload.get("split_summary"), 80),
        gear_tags=_clean_str_list(payload.get("gear_tags"), allowed=PLAN_GEAR_TAGS),
        description=_opt_str(payload.get("description"), 4000),
        cover_url=_opt_str(payload.get("cover_url"), 512),
        is_published=bool(payload.get("is_published", False)),
        sort_order=int(payload.get("sort_order") or 0),
        created_at=now,
        updated_at=now,
    )
    session.add(tpl)
    session.commit()
    return get_admin_plan(session, plan_id)


def update_admin_plan(session: Session, plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    tpl = session.get(PlanTemplate, plan_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="计划不存在")

    if "title" in payload and payload["title"] is not None:
        title = str(payload["title"]).strip()
        if not title:
            raise HTTPException(status_code=400, detail="标题不能为空")
        tpl.title = title
    if "subtitle" in payload:
        tpl.subtitle = _opt_str(payload.get("subtitle"), 160)
    if "author" in payload:
        tpl.author = _opt_str(payload.get("author"), 80)
    if "badge_label" in payload:
        tpl.badge_label = _opt_str(payload.get("badge_label"), 40)
    if "template_type" in payload and payload["template_type"] is not None:
        tt = str(payload["template_type"]).strip()
        if tt not in TEMPLATE_TYPES:
            raise HTTPException(status_code=400, detail="template_type 无效")
        tpl.template_type = tt
    if "level" in payload:
        level_s = _opt_str(payload.get("level"), 16)
        if level_s and level_s not in LEVELS:
            raise HTTPException(status_code=400, detail="level 无效")
        tpl.level = level_s
    if "days_per_week" in payload and payload["days_per_week"] is not None:
        tpl.days_per_week = max(1, min(7, int(payload["days_per_week"])))
    if "minutes_min" in payload:
        tpl.minutes_min = _opt_int(payload.get("minutes_min"))
    if "minutes_max" in payload:
        tpl.minutes_max = _opt_int(payload.get("minutes_max"))
    if "muscle_tags" in payload:
        tpl.muscle_tags = _clean_str_list(payload.get("muscle_tags"))
    if "split_summary" in payload:
        tpl.split_summary = _opt_str(payload.get("split_summary"), 80)
    if "gear_tags" in payload:
        tpl.gear_tags = _clean_str_list(payload.get("gear_tags"), allowed=PLAN_GEAR_TAGS)
    if "description" in payload:
        tpl.description = _opt_str(payload.get("description"), 4000)
    if "cover_url" in payload:
        tpl.cover_url = _opt_str(payload.get("cover_url"), 512)
    if "is_published" in payload and payload["is_published"] is not None:
        tpl.is_published = bool(payload["is_published"])
    if "sort_order" in payload and payload["sort_order"] is not None:
        tpl.sort_order = int(payload["sort_order"])

    tpl.updated_at = utcnow()
    session.add(tpl)
    session.commit()
    return get_admin_plan(session, plan_id)


def delete_admin_plan(session: Session, plan_id: str) -> dict[str, Any]:
    tpl = session.get(PlanTemplate, plan_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="计划不存在")
    session.delete(tpl)
    session.commit()
    # 清封面目录（忽略失败）
    folder = _PLANS_ROOT / plan_id
    if folder.exists() and folder.is_dir():
        for child in folder.glob("*"):
            try:
                child.unlink()
            except OSError:
                pass
        try:
            folder.rmdir()
        except OSError:
            pass
    return {"ok": True, "id": plan_id}


def create_block(session: Session, plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    tpl = session.get(PlanTemplate, plan_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="计划不存在")
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="板块标题不能为空")
    max_order = session.exec(
        select(func.max(PlanBlock.order_index)).where(PlanBlock.template_id == plan_id)
    ).one()
    order_index = int(payload["order_index"]) if payload.get("order_index") is not None else int(max_order or -1) + 1
    block = PlanBlock(
        template_id=plan_id,
        order_index=order_index,
        title=title,
        muscles=_clean_str_list(payload.get("muscles")),
        minutes_min=_opt_int(payload.get("minutes_min")),
        minutes_max=_opt_int(payload.get("minutes_max")),
        cover_url=_opt_str(payload.get("cover_url"), 512),
        note=_opt_str(payload.get("note"), 2000),
    )
    session.add(block)
    tpl.updated_at = utcnow()
    session.add(tpl)
    session.commit()
    session.refresh(block)
    return _block_out(session, block)


def update_block(session: Session, block_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    block = session.get(PlanBlock, block_id)
    if not block:
        raise HTTPException(status_code=404, detail="板块不存在")
    if "title" in payload and payload["title"] is not None:
        title = str(payload["title"]).strip()
        if not title:
            raise HTTPException(status_code=400, detail="板块标题不能为空")
        block.title = title
    if "muscles" in payload:
        block.muscles = _clean_str_list(payload.get("muscles"))
    if "minutes_min" in payload:
        block.minutes_min = _opt_int(payload.get("minutes_min"))
    if "minutes_max" in payload:
        block.minutes_max = _opt_int(payload.get("minutes_max"))
    if "cover_url" in payload:
        block.cover_url = _opt_str(payload.get("cover_url"), 512)
    if "note" in payload:
        block.note = _opt_str(payload.get("note"), 2000)
    if "order_index" in payload and payload["order_index"] is not None:
        block.order_index = int(payload["order_index"])
    session.add(block)
    tpl = session.get(PlanTemplate, block.template_id)
    if tpl:
        tpl.updated_at = utcnow()
        session.add(tpl)
    session.commit()
    session.refresh(block)
    return _block_out(session, block)


def delete_block(session: Session, block_id: int) -> dict[str, Any]:
    block = session.get(PlanBlock, block_id)
    if not block:
        raise HTTPException(status_code=404, detail="板块不存在")
    plan_id = block.template_id
    session.delete(block)
    tpl = session.get(PlanTemplate, plan_id)
    if tpl:
        tpl.updated_at = utcnow()
        session.add(tpl)
    session.commit()
    return {"ok": True, "id": block_id}


def create_plan_exercise(session: Session, block_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    block = session.get(PlanBlock, block_id)
    if not block:
        raise HTTPException(status_code=404, detail="板块不存在")
    max_order = session.exec(
        select(func.max(PlanExercise.order_index)).where(PlanExercise.block_id == block_id)
    ).one()
    order_index = (
        int(payload["order_index"]) if payload.get("order_index") is not None else int(max_order or -1) + 1
    )
    role = str(payload.get("role") or "main").strip()
    if role not in PLAN_SLOT_ROLES:
        raise HTTPException(status_code=400, detail="role 无效")
    lock_level = str(payload.get("lock_level") or "slot").strip()
    if lock_level not in LOCK_LEVELS:
        raise HTTPException(status_code=400, detail="lock_level 无效")

    exercise_id = _opt_str(payload.get("exercise_id"), 32)
    exercise_name = _opt_str(payload.get("exercise_name"), 120)
    if exercise_id:
        sku = session.get(Exercise, exercise_id)
        if not sku:
            raise HTTPException(status_code=400, detail="动作 SKU 不存在")
        if not exercise_name:
            exercise_name = sku.name_zh

    row = PlanExercise(
        block_id=block_id,
        order_index=order_index,
        exercise_id=exercise_id,
        exercise_name=exercise_name,
        role=role,
        lock_level=lock_level,
        target_sets=_opt_int(payload.get("target_sets")),
        target_reps=_opt_str(payload.get("target_reps"), 32),
        warmup_sets=max(0, min(10, int(payload.get("warmup_sets") or 0))),
        alternatives=_clean_str_list(payload.get("alternatives"), limit=12),
        note=_opt_str(payload.get("note"), 1000),
    )
    session.add(row)
    tpl = session.get(PlanTemplate, block.template_id)
    if tpl:
        tpl.updated_at = utcnow()
        session.add(tpl)
    session.commit()
    session.refresh(row)
    return _exercise_out(session, row)


def update_plan_exercise(session: Session, ex_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = session.get(PlanExercise, ex_id)
    if not row:
        raise HTTPException(status_code=404, detail="动作行不存在")
    if "exercise_id" in payload:
        exercise_id = _opt_str(payload.get("exercise_id"), 32)
        row.exercise_id = exercise_id
        if exercise_id:
            sku = session.get(Exercise, exercise_id)
            if not sku:
                raise HTTPException(status_code=400, detail="动作 SKU 不存在")
            if "exercise_name" not in payload or not payload.get("exercise_name"):
                row.exercise_name = sku.name_zh
    if "exercise_name" in payload:
        row.exercise_name = _opt_str(payload.get("exercise_name"), 120)
    if "role" in payload and payload["role"] is not None:
        role = str(payload["role"]).strip()
        if role not in PLAN_SLOT_ROLES:
            raise HTTPException(status_code=400, detail="role 无效")
        row.role = role
    if "lock_level" in payload and payload["lock_level"] is not None:
        lock_level = str(payload["lock_level"]).strip()
        if lock_level not in LOCK_LEVELS:
            raise HTTPException(status_code=400, detail="lock_level 无效")
        row.lock_level = lock_level
    if "target_sets" in payload:
        row.target_sets = _opt_int(payload.get("target_sets"))
    if "target_reps" in payload:
        row.target_reps = _opt_str(payload.get("target_reps"), 32)
    if "warmup_sets" in payload and payload["warmup_sets"] is not None:
        row.warmup_sets = max(0, min(10, int(payload["warmup_sets"])))
    if "alternatives" in payload:
        row.alternatives = _clean_str_list(payload.get("alternatives"), limit=12)
    if "note" in payload:
        row.note = _opt_str(payload.get("note"), 1000)
    if "order_index" in payload and payload["order_index"] is not None:
        row.order_index = int(payload["order_index"])
    session.add(row)
    block = session.get(PlanBlock, row.block_id)
    if block:
        tpl = session.get(PlanTemplate, block.template_id)
        if tpl:
            tpl.updated_at = utcnow()
            session.add(tpl)
    session.commit()
    session.refresh(row)
    return _exercise_out(session, row)


def delete_plan_exercise(session: Session, ex_id: int) -> dict[str, Any]:
    row = session.get(PlanExercise, ex_id)
    if not row:
        raise HTTPException(status_code=404, detail="动作行不存在")
    session.delete(row)
    session.commit()
    return {"ok": True, "id": ex_id}


def _process_landscape_cover(data: bytes) -> tuple[bytes, str]:
    try:
        from PIL import Image
    except Exception:
        return data, ".jpg"

    img = Image.open(BytesIO(data))
    img = img.convert("RGB")
    w, h = img.size
    max_w = 1600
    if w > max_w:
        nh = max(1, int(h * (max_w / w)))
        img = img.resize((max_w, nh))
    out = BytesIO()
    img.save(out, format="JPEG", quality=88, optimize=True)
    return out.getvalue(), ".jpg"


async def upload_plan_cover(session: Session, plan_id: str, file: UploadFile) -> dict[str, Any]:
    tpl = session.get(PlanTemplate, plan_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="计划不存在")
    filename = file.filename or "cover.bin"
    ext = Path(filename).suffix.lower()
    if ext not in _IMAGE_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '(无扩展名)'}")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件过大（上限 12MB）")

    payload, save_ext = _process_landscape_cover(raw)
    folder = _PLANS_ROOT / plan_id
    folder.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]
    out_name = f"cover_{token}{save_ext}"
    (folder / out_name).write_bytes(payload)
    url = f"/static/plans/{plan_id}/{out_name}"
    tpl.cover_url = url
    tpl.updated_at = utcnow()
    session.add(tpl)
    session.commit()
    return get_admin_plan(session, plan_id)


def _opt_str(value: Any, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
