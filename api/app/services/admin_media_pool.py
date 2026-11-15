"""A3 批量上传与待关联池。"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlmodel import Session, col, func, select

from app.exercises_catalog import reload_all
from app.models import Exercise, ExerciseAlias, ExerciseMedia, MediaUnmatchedPool, utcnow
from app.services.admin_catalog import MEDIA_ROLES, media_url
from app.services import admin_editor

_STATIC_ROOT = Path(__file__).resolve().parents[2] / "static" / "exercises"
_POOL_ROOT = _STATIC_ROOT / "pool"
_MAX_UPLOAD_BYTES = 40 * 1024 * 1024
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_GIF_EXTS = {".gif"}
_VIDEO_EXTS = {".mp4", ".webm", ".mov"}


def _norm_token(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (text or "").lower())


def guess_role(relative_path: str, filename: str) -> str:
    blob = f"{relative_path} {filename}".lower()
    stem = Path(filename).stem.lower()
    if any(k in blob for k in ("highlight", "高光", "clip")):
        return "highlight_video"
    if any(k in blob for k in ("tip", "纠错", "mistake", "error")):
        return "tip"
    if any(k in blob for k in ("demo", "动图", "gif", "animation")):
        return "demo"
    if any(k in blob for k in ("end", "结束", "finish", "bottom")) or stem in {"1", "01"}:
        return "end"
    if any(k in blob for k in ("start", "起始", "begin", "top")) or stem in {"0", "00"}:
        return "start"
    ext = Path(filename).suffix.lower()
    if ext in _GIF_EXTS:
        return "demo"
    if ext in _VIDEO_EXTS:
        return "highlight_video"
    return "start"


def _file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _GIF_EXTS:
        return "gif"
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _IMAGE_EXTS:
        return "image"
    return "other"


def _path_tokens(relative_path: str, filename: str) -> list[str]:
    parts = re.split(r"[\\/]+", relative_path or "")
    parts.append(Path(filename).stem)
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part or part in {".", ".."}:
            continue
        out.append(part)
        # Barbell_Squat → Barbell Squat
        if "_" in part:
            out.append(part.replace("_", " "))
    return out


def find_candidates(session: Session, relative_path: str, filename: str, *, limit: int = 5) -> list[dict[str, Any]]:
    tokens = _path_tokens(relative_path, filename)
    scored: dict[str, dict[str, Any]] = {}

    def add(ex: Exercise, score: int, reason: str) -> None:
        if not ex or not ex.is_valid_exercise:
            return
        cur = scored.get(ex.id)
        if cur and cur["score"] >= score:
            return
        scored[ex.id] = {
            "id": ex.id,
            "name_zh": ex.name_zh,
            "name_en": ex.name_en,
            "fdb_id": ex.fdb_id,
            "muscle": ex.muscle,
            "score": score,
            "reason": reason,
        }

    for token in tokens:
        tnorm = _norm_token(token)
        if not tnorm:
            continue
        # exact id
        ex = session.get(Exercise, token)
        if ex:
            add(ex, 100, "id")
        # padded numeric id
        if token.isdigit():
            padded = token.zfill(4)
            ex = session.get(Exercise, padded)
            if ex:
                add(ex, 100, "id")

        # fdb_id
        rows = session.exec(select(Exercise).where(Exercise.fdb_id == token).limit(3)).all()
        for row in rows:
            add(row, 95, "fdb_id")

        # name_en / folder-style
        like = f"%{token.replace('_', ' ')}%"
        rows = session.exec(
            select(Exercise)
            .where(
                Exercise.is_valid_exercise.is_(True),
                col(Exercise.name_en).ilike(like),
            )
            .limit(8)
        ).all()
        for row in rows:
            en_norm = _norm_token(row.name_en or "")
            score = 90 if en_norm == tnorm else 70 if tnorm and tnorm in en_norm else 55
            add(row, score, "name_en")

        # name_zh
        if re.search(r"[\u4e00-\u9fff]", token):
            rows = session.exec(
                select(Exercise)
                .where(
                    Exercise.is_valid_exercise.is_(True),
                    col(Exercise.name_zh).contains(token),
                )
                .limit(8)
            ).all()
            for row in rows:
                score = 92 if row.name_zh == token else 68
                add(row, score, "name_zh")

        # alias
        aliases = session.exec(
            select(ExerciseAlias).where(
                ExerciseAlias.status == "published",
                col(ExerciseAlias.alias).ilike(f"%{token}%"),
            ).limit(8)
        ).all()
        for alias in aliases:
            ex = session.get(Exercise, alias.exercise_id)
            if ex:
                score = 88 if alias.alias == token else 60
                add(ex, score, "alias")

    ranked = sorted(scored.values(), key=lambda x: (-x["score"], x["name_zh"]))
    return ranked[:limit]


def resolve_match(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    top = candidates[0]
    if top["score"] >= 90:
        # unique high confidence
        if len(candidates) == 1 or candidates[1]["score"] < top["score"] - 10:
            return top
    if top["score"] >= 95:
        return top
    return None


def _pool_item(row: MediaUnmatchedPool) -> dict[str, Any]:
    return {
        "id": row.id,
        "filename": row.filename,
        "relative_path": row.relative_path,
        "url": media_url(row.stored_path),
        "file_type": row.file_type,
        "size_bytes": row.size_bytes,
        "guessed_role": row.guessed_role,
        "candidates": row.candidates or [],
        "status": row.status,
        "bound_exercise_id": row.bound_exercise_id,
        "bound_media_id": row.bound_media_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_pool(
    session: Session,
    *,
    status: str | None = "pending",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    stmt = select(MediaUnmatchedPool)
    count_stmt = select(func.count()).select_from(MediaUnmatchedPool)
    if status:
        stmt = stmt.where(MediaUnmatchedPool.status == status)
        count_stmt = count_stmt.where(MediaUnmatchedPool.status == status)
    total = int(session.exec(count_stmt).one() or 0)
    rows = session.exec(
        stmt.order_by(col(MediaUnmatchedPool.created_at).desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_pool_item(row) for row in rows],
    }


async def batch_upload(
    session: Session,
    files: list[UploadFile],
    relative_paths: list[str] | None = None,
    *,
    publish: bool = False,
) -> dict[str, Any]:
    _POOL_ROOT.mkdir(parents=True, exist_ok=True)
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for idx, upload in enumerate(files):
        filename = upload.filename or f"file_{idx}"
        rel = ""
        if relative_paths and idx < len(relative_paths):
            rel = (relative_paths[idx] or "").replace("\\", "/")
        if not rel:
            rel = filename
        try:
            raw = await upload.read()
            if not raw:
                raise ValueError("空文件")
            if len(raw) > _MAX_UPLOAD_BYTES:
                raise ValueError("文件过大（上限 40MB）")
            ext = Path(filename).suffix.lower()
            allowed = _IMAGE_EXTS | _GIF_EXTS | _VIDEO_EXTS
            if ext not in allowed:
                raise ValueError(f"不支持的类型: {ext or '(无扩展名)'}")

            role = guess_role(rel, filename)
            if role not in MEDIA_ROLES:
                role = "start"
            candidates = find_candidates(session, rel, filename)
            hit = resolve_match(candidates)

            if hit:
                detail = admin_editor.save_media_bytes(
                    session,
                    hit["id"],
                    role=role,
                    filename=filename,
                    raw=raw,
                    publish=publish,
                    source="batch",
                )
                matched.append(
                    {
                        "filename": filename,
                        "relative_path": rel,
                        "exercise_id": hit["id"],
                        "name_zh": hit["name_zh"],
                        "role": role,
                        "reason": hit["reason"],
                        "media_status": "published" if publish else "draft",
                        "detail_id": detail["id"],
                    }
                )
            else:
                token = uuid.uuid4().hex[:12]
                folder = _POOL_ROOT / token
                folder.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r"[^a-zA-Z0-9._\u4e00-\u9fff-]+", "_", filename)[:80] or "file"
                abs_path = folder / safe
                abs_path.write_bytes(raw)
                stored = f"pool/{token}/{safe}".replace("\\", "/")
                row = MediaUnmatchedPool(
                    filename=filename,
                    relative_path=rel,
                    stored_path=stored,
                    file_type=_file_type(filename),
                    size_bytes=len(raw),
                    guessed_role=role,
                    candidates=candidates,
                    status="pending",
                )
                session.add(row)
                session.commit()
                session.refresh(row)
                unmatched.append(_pool_item(row))
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "filename": filename,
                    "relative_path": rel,
                    "error": str(exc),
                }
            )

    if matched and publish:
        reload_all()

    return {
        "matched": matched,
        "unmatched": unmatched,
        "errors": errors,
        "summary": {
            "total": len(files),
            "matched": len(matched),
            "unmatched": len(unmatched),
            "errors": len(errors),
        },
    }


def bind_pool_item(
    session: Session,
    pool_id: int,
    *,
    exercise_id: str,
    role: str | None = None,
    publish: bool = False,
) -> dict[str, Any]:
    row = session.get(MediaUnmatchedPool, pool_id)
    if not row:
        raise HTTPException(status_code=404, detail="池条目不存在")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail=f"当前状态不可绑定: {row.status}")
    ex = session.get(Exercise, exercise_id)
    if not ex or not ex.is_valid_exercise:
        raise HTTPException(status_code=404, detail="动作不存在")

    use_role = role or row.guessed_role or "start"
    if use_role not in MEDIA_ROLES:
        raise HTTPException(status_code=400, detail=f"无效槽位: {use_role}")

    abs_path = _STATIC_ROOT / row.stored_path
    if not abs_path.exists():
        raise HTTPException(status_code=400, detail="池文件已丢失")
    raw = abs_path.read_bytes()
    detail = admin_editor.save_media_bytes(
        session,
        exercise_id,
        role=use_role,
        filename=row.filename,
        raw=raw,
        publish=publish,
        source="batch_bind",
    )
    # find latest media id for this role
    media_rows = session.exec(
        select(ExerciseMedia)
        .where(
            ExerciseMedia.exercise_id == exercise_id,
            ExerciseMedia.role == use_role,
        )
        .order_by(col(ExerciseMedia.created_at).desc())
    ).all()
    media_id = media_rows[0].id if media_rows else None

    row.status = "bound"
    row.bound_exercise_id = exercise_id
    row.bound_media_id = media_id
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    if publish:
        reload_all()
    return {
        "pool": _pool_item(row),
        "exercise": {"id": detail["id"], "name_zh": detail["name_zh"]},
        "role": use_role,
    }


def ignore_pool_item(session: Session, pool_id: int) -> dict[str, Any]:
    row = session.get(MediaUnmatchedPool, pool_id)
    if not row:
        raise HTTPException(status_code=404, detail="池条目不存在")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail=f"当前状态不可忽略: {row.status}")
    row.status = "ignored"
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _pool_item(row)


def search_exercises_for_bind(session: Session, q: str, *, limit: int = 12) -> list[dict[str, Any]]:
    q = (q or "").strip()
    if not q:
        return []
    return find_candidates(session, q, q, limit=limit)
