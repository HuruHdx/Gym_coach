"""内容工坊：批量贴口令 → 下载/字幕/拆计划 → 审核发布。"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlmodel import Session, col, select

# UploadFile 仅 upload_fallback 使用

from app.exercises_catalog import ensure_loaded, find_catalog_mentions_in_text
from app.models import (
    Exercise,
    ExerciseAlias,
    ExerciseMedia,
    PlanBlock,
    PlanExercise,
    PlanTemplate,
    StudioTask,
    utcnow,
)
from app.services.media_clip import ffmpeg_available, make_demo_pair
from app.services.storage import save_public_asset
from app.exercise_match import repair_spoken_name, resolve_spoken_match
from app.taxonomy import canonicalize_exercise

_API_ROOT = Path(__file__).resolve().parents[2]
_STUDIO_ROOT = _API_ROOT / "static" / "studio"
_COOKIE_FILE = _API_ROOT / "data" / "studio_cookies.json"
_DATA_DIR = _API_ROOT / "data"

_URL_RE = re.compile(
    r"https?://[^\s<>\"']+|(?:www\.)?douyin\.com/[^\s<>\"']+|v\.douyin\.com/[A-Za-z0-9_-]+|b23\.tv/[A-Za-z0-9_-]+",
    re.I,
)
_DOUYIN_MODAL_RE = re.compile(r"[?&]modal_id=(\d+)", re.I)
_DOUYIN_VIDEO_RE = re.compile(r"douyin\.com/video/(\d+)", re.I)
_SETS_RE = re.compile(
    r"(?P<sets>\d+)\s*组.*?((?P<reps_a>\d+)\s*[-~到至]\s*(?P<reps_b>\d+)|(?P<reps>\d+)\s*次)",
    re.S,
)
_KNOWN_MUSCLES = {"胸", "背", "肩", "腿", "臂", "核心", "全身"}
_RELINK_STATUSES = (
    "needs_manual_upload",
    "failed",
    "queued",
    "downloading",
    "done",
)


def _task_dir(task_id: int) -> Path:
    d = _STUDIO_ROOT / str(task_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _touch(task: StudioTask, **fields: Any) -> None:
    for k, v in fields.items():
        setattr(task, k, v)
    task.updated_at = utcnow()


def normalize_media_url(raw: str) -> str:
    """把分享口令 / 用户页 modal 链归一成可下载 URL。"""
    url = (raw or "").strip().rstrip(")。.,，、]")
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith(("v.douyin.com", "b23.tv", "douyin.com", "www.douyin.com")):
        url = "https://" + url
    # 用户页弹窗：...?modal_id=123 → https://www.douyin.com/video/123
    m = _DOUYIN_MODAL_RE.search(url)
    if m and "douyin.com" in url.lower():
        return f"https://www.douyin.com/video/{m.group(1)}"
    m2 = _DOUYIN_VIDEO_RE.search(url)
    if m2:
        return f"https://www.douyin.com/video/{m2.group(1)}"
    return url


def extract_urls(text: str) -> list[str]:
    found: list[str] = []
    for m in _URL_RE.finditer(text or ""):
        raw = normalize_media_url(m.group(0))
        if raw and raw not in found:
            found.append(raw)
    return found[:10]


def _reset_task_media(task_id: int) -> None:
    for stale in _task_dir(task_id).glob("source.*"):
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            pass


_COOKIE_BROWSERS = ("chrome", "edge", "firefox", "brave", "chromium")


def save_cookies(payload: dict[str, Any]) -> dict[str, Any]:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    source = str(payload.get("source") or "paste").strip().lower()
    if source not in ("paste", "browser"):
        source = "paste"
    browser = str(payload.get("browser") or "chrome").strip().lower()
    if browser not in _COOKIE_BROWSERS:
        browser = "chrome"
    clean = {
        "source": source,
        "browser": browser,
        "bilibili": str(payload.get("bilibili") or "").strip(),
        "douyin": str(payload.get("douyin") or "").strip(),
        "youtube": str(payload.get("youtube") or "").strip(),
        "updated_at": utcnow().isoformat(),
    }
    _COOKIE_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "updated_at": clean["updated_at"], "source": source, "browser": browser}


def load_cookies() -> dict[str, Any]:
    empty = {
        "source": "paste",
        "browser": "chrome",
        "bilibili": "",
        "douyin": "",
        "youtube": "",
        "updated_at": None,
    }
    if not _COOKIE_FILE.exists():
        return empty
    try:
        data = json.loads(_COOKIE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return empty
    if not isinstance(data, dict):
        return empty
    source = str(data.get("source") or "paste").lower()
    browser = str(data.get("browser") or "chrome").lower()
    return {
        **empty,
        **data,
        "source": source if source in ("paste", "browser") else "paste",
        "browser": browser if browser in _COOKIE_BROWSERS else "chrome",
    }


def _pipeline_step(task: StudioTask) -> str:
    st = task.status
    if st in ("queued", "downloading"):
        return "download"
    if st == "awaiting_confirm":
        return "downloaded"
    if st == "transcribing":
        return "transcribe"
    if st == "parsing":
        return "parse"
    if st in ("done",):
        return "review"
    if st in ("needs_manual_upload", "failed"):
        return "download"
    return st


def studio_deps() -> dict[str, Any]:
    ytdlp = False
    try:
        import yt_dlp  # noqa: F401

        ytdlp = True
    except Exception:
        ytdlp = bool(shutil.which("yt-dlp"))
    whisper = False
    try:
        import faster_whisper  # noqa: F401

        whisper = True
    except Exception:
        whisper = False
    from app.brain.llm import MockLLM, get_llm
    from app.config import settings

    llm_ok = not isinstance(get_llm(), MockLLM)
    return {
        "yt_dlp": ytdlp,
        "ffmpeg": ffmpeg_available(),
        "faster_whisper": whisper,
        "llm": llm_ok,
        "llm_model": settings.llm_model if llm_ok else None,
        "cookie_source": (load_cookies().get("source") or "paste"),
    }


def _hydrate_demo_covers(draft: dict[str, Any], session: Session | None) -> dict[str, Any]:
    """clipped 但缺 demo_cover_url 时，用 SKU image_start 回填（旧草稿兼容）。"""
    if not session or not isinstance(draft, dict):
        return draft
    need_ids: list[str] = []
    for block in draft.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        for ex in block.get("exercises") or []:
            if not isinstance(ex, dict):
                continue
            if (ex.get("media_status") != "clipped") or ex.get("demo_cover_url"):
                continue
            eid = str(ex.get("exercise_id") or "").strip()
            if eid:
                need_ids.append(eid)
    if not need_ids:
        return draft
    rows = session.exec(select(Exercise).where(col(Exercise.id).in_(list(set(need_ids))))).all()
    by_id = {str(r.id): r for r in rows}
    changed = False
    for block in draft.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        for ex in block.get("exercises") or []:
            if not isinstance(ex, dict):
                continue
            if (ex.get("media_status") != "clipped") or ex.get("demo_cover_url"):
                continue
            sku = by_id.get(str(ex.get("exercise_id") or ""))
            if sku and sku.image_start:
                ex["demo_cover_url"] = sku.image_start
                changed = True
    return draft if changed else draft


def _task_out(task: StudioTask, session: Session | None = None) -> dict[str, Any]:
    play_url = None
    if task.stored_path:
        p = task.stored_path.replace("\\", "/")
        play_url = p if p.startswith(("http://", "https://", "/static/")) else f"/static/{p}"
    draft = task.draft_json or {}
    if isinstance(draft, dict):
        draft = _hydrate_demo_covers(dict(draft), session)
    exercises = []
    if isinstance(draft, dict):
        for b in draft.get("blocks") or []:
            exercises.extend(b.get("exercises") or [])
    clipped = sum(1 for e in exercises if (e or {}).get("media_status") == "clipped")
    return {
        "id": task.id,
        "batch_id": task.batch_id,
        "batch_order": task.batch_order,
        "source_type": task.source_type,
        "source_text": task.source_text,
        "source_url": task.source_url,
        "stored_path": task.stored_path,
        "play_url": play_url,
        "mode": task.mode,
        "status": task.status,
        "progress": task.progress,
        "pipeline_step": _pipeline_step(task),
        "transcript_json": task.transcript_json or {},
        "draft_json": draft,
        "score": task.score or {},
        "review_state": task.review_state,
        "result_ref": task.result_ref or {},
        "error": task.error,
        "exercise_count": len(exercises),
        "clipped_count": clipped,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def list_tasks(session: Session, *, limit: int = 50) -> dict[str, Any]:
    rows = list(
        session.exec(
            select(StudioTask).order_by(col(StudioTask.id).desc()).limit(max(1, min(200, limit)))
        ).all()
    )
    # 列表不回填封面（省查询）；详情 get_task 才会 hydrate
    return {"items": [_task_out(t) for t in rows], "total": len(rows)}


def get_task(session: Session, task_id: int) -> dict[str, Any]:
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_out(task, session)


def ingest_batch(
    session: Session,
    *,
    text: str | None = None,
    mode: str = "plan_single",
    merge_into_one_plan: bool = False,
    plan_title: str | None = None,
    files: list[tuple[str, bytes]] | None = None,
    pause_for_confirm: bool = False,
    source_kind: str | None = None,
) -> dict[str, Any]:
    mode = mode if mode in ("plan_single", "plan_merge", "exercise_only") else "plan_single"
    if merge_into_one_plan:
        mode = "plan_merge"

    urls = extract_urls(text or "")
    uploads = files or []
    if not urls and not uploads:
        raise HTTPException(status_code=400, detail="请粘贴分享口令/链接，或上传本地视频")

    batch_id = uuid.uuid4().hex[:16] if (mode == "plan_merge" and (len(urls) + len(uploads)) > 1) else None
    title = (plan_title or "").strip() or None
    created: list[StudioTask] = []
    order = 0
    link_type = "direct" if (source_kind or "").strip() == "direct" else "link"

    for url in urls:
        draft0: dict[str, Any] = {}
        if title:
            draft0["plan_title"] = title
        if pause_for_confirm:
            draft0["pause_for_confirm"] = True
        task = StudioTask(
            batch_id=batch_id,
            batch_order=order,
            source_type=link_type,
            source_text=(text or "")[:2000] if order == 0 else url,
            source_url=url,
            mode=mode,
            status="queued",
            progress=0,
            draft_json=draft0,
            review_state="needs_review",
        )
        session.add(task)
        session.flush()
        created.append(task)
        order += 1

    for filename, raw in uploads:
        if not raw:
            continue
        draft0: dict[str, Any] = {}
        if title:
            draft0["plan_title"] = title
        if pause_for_confirm:
            draft0["pause_for_confirm"] = True
        task = StudioTask(
            batch_id=batch_id,
            batch_order=order,
            source_type="upload",
            source_text=filename,
            source_url=None,
            mode=mode,
            status="queued",
            progress=5,
            draft_json=draft0,
            review_state="needs_review",
        )
        session.add(task)
        session.flush()
        assert task.id is not None
        safe_name = Path(filename or "upload.mp4").name
        dest = _task_dir(task.id) / safe_name
        dest.write_bytes(raw)
        task.stored_path = f"/static/studio/{task.id}/{safe_name}"
        created.append(task)
        order += 1

    session.commit()
    for t in created:
        session.refresh(t)
        _spawn_pipeline(t.id)

    return {"batch_id": batch_id, "items": [_task_out(t) for t in created]}


async def upload_fallback(session: Session, task_id: int, file: UploadFile) -> dict[str, Any]:
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    dest = _task_dir(task_id) / (file.filename or "fallback.mp4")
    dest.write_bytes(raw)
    _touch(
        task,
        stored_path=f"/static/studio/{task_id}/{dest.name}",
        source_type="upload",
        status="queued",
        progress=5,
        error=None,
    )
    session.add(task)
    session.commit()
    _spawn_pipeline(task_id)
    return get_task(session, task_id)


def retry_download(session: Session, task_id: int) -> dict[str, Any]:
    """Cookie 配好后，对需补传/失败的链接任务重新走下载流水线。"""
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.source_url:
        raise HTTPException(status_code=400, detail="该任务没有源链接，请改用补传本地 MP4")
    if task.status not in (*_RELINK_STATUSES, "awaiting_confirm"):
        raise HTTPException(status_code=400, detail=f"当前状态「{task.status}」不可重试下载")
    _reset_task_media(task_id)
    ref = dict(task.result_ref or {})
    ref.pop("continued", None)
    _touch(
        task,
        stored_path=None,
        source_type=task.source_type or "link",
        status="queued",
        progress=0,
        error=None,
        transcript_json=None,
        result_ref=ref,
    )
    session.add(task)
    session.commit()
    _spawn_pipeline(task_id)
    return get_task(session, task_id)


def continue_pipeline(session: Session, task_id: int) -> dict[str, Any]:
    """「先停住等确认」之后继续转字幕 / 拆计划。"""
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in ("awaiting_confirm", "needs_manual_upload", "done", "failed"):
        raise HTTPException(status_code=400, detail=f"当前状态「{task.status}」不可继续")
    if not _abs_video(task):
        raise HTTPException(status_code=400, detail="还没有本地视频")
    ref = dict(task.result_ref or {})
    ref["continued"] = True
    _touch(task, status="queued", progress=35, error=None, result_ref=ref)
    session.add(task)
    session.commit()
    _spawn_pipeline(task_id)
    return get_task(session, task_id)


def retranscribe(session: Session, task_id: int) -> dict[str, Any]:
    """重跑字幕 + 拆计划（视频已在本地）。"""
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not _abs_video(task):
        raise HTTPException(status_code=400, detail="还没有本地视频，请先下载或补传")
    ref = dict(task.result_ref or {})
    ref["continued"] = True
    _touch(
        task,
        status="queued",
        progress=35,
        error=None,
        transcript_json=None,
        result_ref=ref,
    )
    session.add(task)
    session.commit()
    _spawn_pipeline(task_id)
    return get_task(session, task_id)


def skip_transcribe(session: Session, task_id: int) -> dict[str, Any]:
    """长视频转写卡住时：作废当前流水线，空字幕进工作台，改手填动作。"""
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not _abs_video(task):
        raise HTTPException(status_code=400, detail="还没有本地视频，请先下载或补传")
    # 作废可能还在跑的旧线程
    _bump_pipeline_run(session, task_id)
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    draft = task.draft_json if isinstance(task.draft_json, dict) else {}
    if not (draft.get("blocks") or []):
        draft = {
            **draft,
            "blocks": [
                {
                    "title": draft.get("plan_title") or "手动板块",
                    "muscles": [],
                    "exercises": [],
                }
            ],
        }
    _touch(
        task,
        status="done",
        progress=100,
        error=None,
        draft_json=draft,
        score={"red_count": 0, "amber_count": 0, "green_count": 0, "total": 0},
        review_state="needs_review",
        transcript_json={
            "engine": "skipped",
            "warning": "已跳过自动字幕（长视频转写太慢或卡住）。请在右栏手填动作，或稍后点「重跑字幕」。",
            "segments": [],
            "text": "",
        },
    )
    _set_live(task, stage="done", percent=100, detail="已跳过字幕")
    session.add(task)
    session.commit()
    return get_task(session, task_id)


def attach_demo_now(
    session: Session,
    *,
    task_id: int,
    exercise_id: str,
    start: float,
    end: float,
) -> dict[str, Any]:
    """立刻把选区压成静音小 MP4 + 封面，写入动作库（不等到发布）。"""
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not session.get(Exercise, exercise_id):
        raise HTTPException(status_code=404, detail="动作 SKU 不存在")
    if end <= start:
        raise HTTPException(status_code=400, detail="选区无效：结束须大于开始")
    if end - start > 30:
        raise HTTPException(status_code=400, detail="示范选区请控制在 30 秒内")
    if not ffmpeg_available():
        raise HTTPException(status_code=400, detail="本机没有 ffmpeg，无法切片")
    meta = _attach_demo_media(session, task, exercise_id, float(start), float(end))
    if not meta:
        raise HTTPException(status_code=400, detail="切片失败：本地视频不存在或 ffmpeg 出错")
    # 方案 A：立刻出库示范只写媒体；要领只在抽屉点「写进库」
    # 封面/示范 URL 写回草稿，刷新后「本次产出」还能出缩略图
    draft = dict(task.draft_json or {}) if isinstance(task.draft_json, dict) else {}
    blocks = list(draft.get("blocks") or [])
    changed = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for ex in block.get("exercises") or []:
            if not isinstance(ex, dict):
                continue
            if str(ex.get("exercise_id") or "") != str(exercise_id):
                continue
            snip = dict(ex.get("snippet") or {})
            snip["start"] = float(start)
            snip["end"] = float(end)
            ex["snippet"] = snip
            ex["media_status"] = "clipped"
            ex["attach_demo"] = True
            ex["demo_url"] = meta.get("demo_url")
            ex["demo_cover_url"] = meta.get("cover_url")
            changed = True
    if changed:
        draft["blocks"] = blocks
        task.draft_json = draft
        task.updated_at = utcnow()
        session.add(task)
    session.commit()
    return {
        "ok": True,
        "exercise_id": exercise_id,
        "demo": meta,
        "synced_text": {"ok": False, "reason": "drawer_only"},
    }


def reparse(session: Session, task_id: int) -> dict[str, Any]:
    """字幕已有时只重跑 LLM/启发式拆计划，不重转写。"""
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    transcript = task.transcript_json or {}
    segs = (transcript.get("segments") if isinstance(transcript, dict) else None) or []
    text = (transcript.get("text") if isinstance(transcript, dict) else None) or ""
    if not segs and not text:
        raise HTTPException(status_code=400, detail="还没有字幕，请先转字幕")
    _touch(task, status="parsing", progress=75, error=None)
    session.add(task)
    session.commit()
    try:
        draft, score = _parse_and_score(session, task, transcript if isinstance(transcript, dict) else {})
        if isinstance(task.draft_json, dict):
            title = task.draft_json.get("plan_title")
            if title and not draft.get("plan_title"):
                draft["plan_title"] = title
        review = (
            "needs_review"
            if score.get("red_count", 0) > 0 or score.get("amber_count", 0) > 0
            else "auto_pass"
        )
        _touch(
            task,
            draft_json=draft,
            score=score,
            review_state=review,
            status="done",
            progress=100,
            error=None,
        )
        session.add(task)
        session.commit()
    except Exception as e:  # noqa: BLE001
        _touch(task, status="failed", error=f"拆计划失败：{str(e)[:400]}", progress=100)
        session.add(task)
        session.commit()
        raise HTTPException(status_code=500, detail=str(e)[:300]) from e
    return get_task(session, task_id)


def replace_source(
    session: Session,
    task_id: int,
    *,
    text: str | None = None,
) -> dict[str, Any]:
    """更换任务源链接（可贴新口令 / 用户页 modal 链 / 直链），然后重新跑流水线。"""
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status not in _RELINK_STATUSES and task.status not in ("transcribing", "parsing"):
        raise HTTPException(status_code=400, detail=f"当前状态「{task.status}」不可更换源")
    urls = extract_urls(text or "")
    if not urls:
        raise HTTPException(status_code=400, detail="未识别到链接；请粘贴抖音/B站分享口令或 URL")
    url = urls[0]
    keep_title = None
    if isinstance(task.draft_json, dict):
        keep_title = task.draft_json.get("plan_title")
    _reset_task_media(task_id)
    _touch(
        task,
        source_type="link",
        source_text=(text or url)[:2000],
        source_url=url,
        stored_path=None,
        status="queued",
        progress=0,
        error=None,
        transcript_json=None,
        draft_json={"plan_title": keep_title} if keep_title else {},
        score={},
        review_state="needs_review",
        result_ref={},
    )
    session.add(task)
    session.commit()
    _spawn_pipeline(task_id)
    return get_task(session, task_id)


def _bump_pipeline_run(session: Session, task_id: int) -> int:
    """每次启动流水线递增 run_id；旧线程发现对不上就自行退出，避免重跑叠跑。"""
    task = session.get(StudioTask, task_id)
    if not task:
        return 0
    ref = dict(task.result_ref or {})
    run_id = int(ref.get("pipeline_run") or 0) + 1
    ref["pipeline_run"] = run_id
    task.result_ref = ref
    session.add(task)
    session.commit()
    return run_id


def _pipeline_run_of(task: StudioTask | None) -> int:
    if not task or not isinstance(task.result_ref, dict):
        return 0
    return int(task.result_ref.get("pipeline_run") or 0)


def _pipeline_still_current(session: Session, task_id: int, run_id: int) -> bool:
    task = session.get(StudioTask, task_id)
    return bool(task) and _pipeline_run_of(task) == run_id


def _spawn_pipeline(task_id: int) -> None:
    from app.db import engine

    with Session(engine) as session:
        run_id = _bump_pipeline_run(session, task_id)
    t = threading.Thread(target=_run_pipeline_safe, args=(task_id, run_id), daemon=True)
    t.start()


def _run_pipeline_safe(task_id: int, run_id: int = 0) -> None:
    from app.db import engine

    try:
        with Session(engine) as session:
            _run_pipeline(session, task_id, run_id=run_id)
    except Exception as e:  # noqa: BLE001
        with Session(engine) as session:
            task = session.get(StudioTask, task_id)
            if not task:
                return
            # 已被更新一轮流水线取代 → 旧线程异常直接丢弃
            if run_id and _pipeline_run_of(task) != run_id:
                return
            # 本地视频还在 → 多半是转字幕挂了，别伪装成「抓不到」
            has_video = bool(_abs_video(task))
            msg = str(e)[:500]
            if has_video and "metadata_errors" in msg:
                msg = (
                    "转字幕失败：faster-whisper 与本机 PyAV 版本不兼容（metadata_errors）。"
                    "已修复兼容层，请点「重跑字幕」。"
                )
            elif has_video:
                msg = f"转字幕/拆计划失败：{msg}"
            _touch(task, status="failed", error=msg, progress=100)
            session.add(task)
            session.commit()


def _abs_video(task: StudioTask) -> Path | None:
    if not task.stored_path:
        return None
    p = task.stored_path
    if p.startswith("/static/"):
        return _API_ROOT / "static" / p[len("/static/") :]
    if p.startswith("static/"):
        return _API_ROOT / p
    cand = Path(p)
    return cand if cand.exists() else None


def _run_pipeline(session: Session, task_id: int, run_id: int = 0) -> None:
    task = session.get(StudioTask, task_id)
    if not task:
        return
    if run_id and _pipeline_run_of(task) != run_id:
        return

    # 1) download
    if not task.stored_path and task.source_url:
        _touch(task, status="downloading", progress=10, error=None)
        _set_live(task, stage="downloading", percent=0)
        session.add(task)
        session.commit()

        def _on_download(meta: dict[str, Any]) -> None:
            if not _pipeline_still_current(session, task_id, run_id):
                return
            fresh = session.get(StudioTask, task_id)
            if not fresh:
                return
            pct = int(meta.get("percent") or 0)
            fresh.progress = min(38, 10 + int(pct * 0.28))
            _set_live(fresh, **meta)
            session.add(fresh)
            session.commit()

        ok, err = _download_url(task, on_progress=_on_download)
        if not _pipeline_still_current(session, task_id, run_id):
            return
        session.refresh(task)
        if not ok:
            _touch(task, status="needs_manual_upload", progress=20, error=err)
            session.add(task)
            session.commit()
            return

    video = _abs_video(task)
    if not video or not video.exists():
        _touch(task, status="needs_manual_upload", progress=20, error="缺少本地视频，请补传 MP4")
        session.add(task)
        session.commit()
        return

    pause = bool((task.draft_json or {}).get("pause_for_confirm")) if isinstance(task.draft_json, dict) else False
    continued = bool((task.result_ref or {}).get("continued")) if isinstance(task.result_ref, dict) else False
    if pause and not continued:
        # 素材已就绪，先停住等确认，再转字幕/拆计划
        _touch(task, status="awaiting_confirm", progress=35, error=None)
        _set_live(task, stage="awaiting_confirm", percent=35)
        session.add(task)
        session.commit()
        return

    # 2) transcribe（长视频会跑很久：进度必须随片段推进，不能钉死在 40%）
    _touch(task, status="transcribing", progress=40)
    _set_live(task, stage="transcribing", percent=40, detail="准备转写…")
    session.add(task)
    session.commit()

    def _on_transcribe(meta: dict[str, Any]) -> None:
        if not _pipeline_still_current(session, task_id, run_id):
            return
        fresh = session.get(StudioTask, task_id)
        if not fresh:
            return
        pct = int(meta.get("percent") or 40)
        fresh.progress = max(40, min(72, pct))
        _set_live(fresh, **meta)
        session.add(fresh)
        session.commit()

    transcript = _transcribe(video, on_progress=_on_transcribe)
    if not _pipeline_still_current(session, task_id, run_id):
        return
    task = session.get(StudioTask, task_id) or task
    task.transcript_json = transcript
    task.progress = 72

    # 3) parse + score
    _touch(task, status="parsing", progress=75)
    _set_live(task, stage="parsing", percent=75, detail="拆动作清单…")
    session.add(task)
    session.commit()
    draft, score = _parse_and_score(session, task, transcript)
    if not _pipeline_still_current(session, task_id, run_id):
        return
    if task.draft_json and isinstance(task.draft_json, dict):
        # 保留 ingest 时的 plan_title
        title = (task.draft_json or {}).get("plan_title")
        if title and not draft.get("plan_title"):
            draft["plan_title"] = title
    review = (
        "needs_review"
        if score.get("red_count", 0) > 0 or score.get("amber_count", 0) > 0
        else "auto_pass"
    )
    _touch(
        task,
        draft_json=draft,
        score=score,
        review_state=review,
        status="done",
        progress=100,
        error=None,
    )
    session.add(task)
    session.commit()


def _cookie_domains_for_url(url: str) -> list[str]:
    u = (url or "").lower()
    if "douyin" in u or "iesdouyin" in u:
        return [".douyin.com", ".iesdouyin.com"]
    if "bilibili" in u or "b23.tv" in u:
        return [".bilibili.com"]
    if "youtube" in u or "youtu.be" in u:
        return [".youtube.com"]
    return [".douyin.com", ".bilibili.com", ".youtube.com"]


def _pick_cookie_blob(cookies: dict[str, Any], url: str) -> str:
    u = (url or "").lower()
    if "douyin" in u or "iesdouyin" in u:
        return str(cookies.get("douyin") or "")
    if "bilibili" in u or "b23.tv" in u:
        return str(cookies.get("bilibili") or "")
    if "youtube" in u or "youtu.be" in u:
        return str(cookies.get("youtube") or "")
    return (
        str(cookies.get("douyin") or "")
        or str(cookies.get("bilibili") or "")
        or str(cookies.get("youtube") or "")
    )


def _to_netscape_cookie_file(blob: str, domains: list[str]) -> str:
    """把浏览器 Cookie 头或已有 Netscape 文本写成 yt-dlp 可读的 cookies.txt。"""
    text = (blob or "").strip()
    if not text:
        return ""
    # 已是 Netscape / 导出扩展格式
    if "\t" in text and ("TRUE" in text or "FALSE" in text):
        return text if text.lstrip().startswith("#") else f"# Netscape HTTP Cookie File\n{text}"
    if "Netscape" in text and "\t" in text:
        return text

    lines = ["# Netscape HTTP Cookie File", "# Converted from Cookie header"]
    for part in text.replace("\n", ";").split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        for domain in domains:
            # domain \t includeSubdomains \t path \t secure \t expiry \t name \t value
            lines.append(f"{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    return "\n".join(lines) + "\n"


_DOWNLOAD_PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<pct>[\d.]+)%"
    r"(?:\s+of\s+~?(?P<size>\S+))?"
    r"(?:\s+at\s+(?P<speed>\S+))?"
    r"(?:\s+ETA\s+(?P<eta>\S+))?",
    re.I,
)


def _referer_for_url(url: str) -> str | None:
    """按域名给 Referer；写死抖音会让 B 站 playurl 直接 403。"""
    u = (url or "").lower()
    if "douyin" in u or "iesdouyin" in u:
        return "https://www.douyin.com/"
    if "bilibili" in u or "b23.tv" in u:
        return "https://www.bilibili.com/"
    if "youtube" in u or "youtu.be" in u:
        return None
    return None


def _friendly_download_error(raw: str, *, url: str = "") -> str:
    text = (raw or "").strip()
    low = text.lower()
    bili = "bilibili" in (url or "").lower() or "b23.tv" in (url or "").lower()
    if "fresh cookies" in low:
        return (
            "平台要求登录态 Cookie。"
            "请用「从本机浏览器读取」或导出 cookies.txt，也可补传本地 MP4。"
        )
    if "http error 403" in low or "403: forbidden" in low:
        if bili:
            return (
                "B站拒绝访问（多为 Referer/风控，公开视频通常不需 Cookie）。"
                "可重试下载、换直链，或补传本地 MP4；只有 1080P+/大会员才需要 SESSDATA。"
            )
        return (
            "平台拒绝访问（403）。"
            "可先不配 Cookie 重试；仍失败再用「从本机浏览器读取」，或补传本地 MP4。"
        )
    if "could not copy" in low and "cookie database" in low:
        return "读不到浏览器 Cookie 库。请先完全退出该浏览器再重试，或改用导出的 cookies.txt。"
    if "private video" in low or "author has closed" in low or "video is unavailable" in low:
        return "作者已关闭或视频不可见。请换一条公开链接，或补传本地 MP4。"
    if "requested format is not available" in low or "no video formats" in low:
        return "这条链接没有可下载的视频格式。请换直链，或补传本地 MP4。"
    if "unsupported url" in low or "no suitable extractor" in low:
        return "不认识这个链接。请贴分享口令、视频页地址，或补传本地 MP4。"
    if "timed out" in low or "network" in low or "connection" in low or "无新进度" in text:
        return text[-400:] if "无新进度" in text else "网络中断或超时。可重新下载，或补传本地 MP4。"
    return text[-800:] if text else "下载失败"


def _set_live(task: StudioTask, **meta: Any) -> None:
    ref = dict(task.result_ref or {})
    ref["live"] = meta
    task.result_ref = ref


def _cookie_args_for_url(url: str, task_id: int) -> list[str]:
    cookies = load_cookies()
    source = str(cookies.get("source") or "paste")
    if source == "browser":
        browser = str(cookies.get("browser") or "chrome")
        return ["--cookies-from-browser", browser]
    blob = _pick_cookie_blob(cookies, url)
    if not blob.strip():
        return []
    jar = _task_dir(task_id) / "cookies.txt"
    jar.write_text(
        _to_netscape_cookie_file(blob, _cookie_domains_for_url(url)),
        encoding="utf-8",
    )
    return ["--cookies", str(jar)]


def _run_ytdlp_once(
    *,
    base_cmd: list[str],
    out_tmpl: str,
    url: str,
    cookie_arg: list[str],
    on_progress: Any = None,
) -> tuple[bool, str, bool]:
    """跑一轮 yt-dlp。返回 (ok, log, stalled)。"""
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    cmd = [
        *base_cmd,
        "--no-playlist",
        "--newline",
        "--socket-timeout",
        "20",
        "--user-agent",
        ua,
    ]
    referer = _referer_for_url(url)
    if referer:
        cmd.extend(["--referer", referer])
    cmd.extend(
        [
            "-f",
            "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "--merge-output-format",
            "mp4",
            "-o",
            out_tmpl,
            *cookie_arg,
            url,
        ]
    )
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    log_lines: list[str] = []
    last_tick = time.monotonic()
    last_emit = 0.0
    stalled = False

    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            q.put(line)
        q.put(None)

    q: queue.Queue[str | None] = queue.Queue()
    threading.Thread(target=_reader, daemon=True).start()
    while True:
        try:
            line = q.get(timeout=1)
        except queue.Empty:
            if time.monotonic() - last_tick > 30:
                stalled = True
                proc.kill()
                break
            if proc.poll() is not None and q.empty():
                break
            continue
        if line is None:
            break
        last_tick = time.monotonic()
        log_lines.append(line.rstrip())
        if len(log_lines) > 80:
            log_lines = log_lines[-80:]
        match = _DOWNLOAD_PROGRESS_RE.search(line)
        if match and on_progress and time.monotonic() - last_emit > 0.6:
            last_emit = time.monotonic()
            on_progress(
                {
                    "stage": "downloading",
                    "percent": int(float(match.group("pct"))),
                    "size": match.group("size"),
                    "speed": match.group("speed"),
                    "eta": match.group("eta"),
                }
            )
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
    log = "\n".join(log_lines)
    ok = (not stalled) and proc.returncode in (0, None)
    return ok, log, stalled


def _download_url(
    task: StudioTask,
    *,
    on_progress: Any = None,
) -> tuple[bool, str | None]:
    assert task.id and task.source_url
    out_tmpl = str(_task_dir(task.id) / "source.%(ext)s")

    # 未 activate venv 时 PATH 里可能没有 yt-dlp.exe，优先 python -m yt_dlp
    ytdlp_bin = shutil.which("yt-dlp")
    if ytdlp_bin:
        base_cmd = [ytdlp_bin]
    else:
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            return False, "未安装 yt-dlp；请补传本地 MP4，或 pip install yt-dlp"
        base_cmd = [sys.executable, "-m", "yt_dlp"]

    cookie_arg = _cookie_args_for_url(task.source_url, task.id)

    def _pick_mp4() -> Path | None:
        files = sorted(_task_dir(task.id).glob("source.*"))
        mp4s = [f for f in files if f.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov")]
        return mp4s[0] if mp4s else None

    # 公开视频（尤其 B 站 480/720P）多数不需要 Cookie：先裸下，失败再带 Cookie 重试
    attempts: list[list[str]] = [[]]
    if cookie_arg:
        attempts.append(cookie_arg)

    last_log = ""
    last_stalled = False
    for i, args in enumerate(attempts):
        if i > 0 and on_progress:
            on_progress({"stage": "downloading", "percent": 0, "size": None, "speed": None, "eta": None})
        ok, log, stalled = _run_ytdlp_once(
            base_cmd=base_cmd,
            out_tmpl=out_tmpl,
            url=task.source_url,
            cookie_arg=args,
            on_progress=on_progress,
        )
        last_log, last_stalled = log, stalled
        dest = _pick_mp4()
        if ok and dest:
            task.stored_path = f"/static/studio/{task.id}/{dest.name}"
            return True, None
        # 无 Cookie 可重试时直接结束；有 Cookie 则进入下一轮
        if i + 1 < len(attempts) and not stalled:
            continue
        break

    if last_stalled:
        return False, "下载超过 30 秒没有新进度，已中断。可重新下载，或补传本地 MP4。"
    return False, _friendly_download_error(last_log or "下载失败", url=task.source_url)


def _patch_av_open_compat() -> None:
    """faster-whisper 会传 metadata_errors=；新版 PyAV(≥14) 已去掉该参数，不补丁会直接 TypeError。"""
    try:
        import av
    except Exception:
        return
    if getattr(av.open, "_gym_compat", False):
        return
    _orig = av.open

    def _open(*args: Any, **kwargs: Any):  # noqa: ANN401
        kwargs.pop("metadata_errors", None)
        return _orig(*args, **kwargs)

    _open._gym_compat = True  # type: ignore[attr-defined]
    av.open = _open  # type: ignore[assignment]


_WHISPER_MODEL: Any = None
_WHISPER_LOCK = threading.Lock()


def _probe_duration_sec(path: Path) -> float | None:
    """用 ffprobe 读时长；失败返回 None。"""
    try:
        from app.services.media_clip import resolve_ffmpeg

        ff = resolve_ffmpeg()
        if not ff:
            return None
        # ffmpeg 同目录常有 ffprobe；没有则用 ffmpeg -i 解析 stderr
        probe = str(Path(ff).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe"))
        if Path(probe).exists():
            out = subprocess.run(
                [
                    probe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            val = float((out.stdout or "").strip() or 0)
            return val if val > 0 else None
        # 回退：ffmpeg -i
        out = subprocess.run(
            [ff, "-i", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out.stderr or "")
        if not m:
            return None
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        return None


def _fmt_hms(sec: float) -> str:
    s = max(0, int(sec))
    h, rem = divmod(s, 3600)
    m, ss = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{ss:02d}"
    return f"{m:02d}:{ss:02d}"


def _get_whisper_model() -> Any:
    """进程内复用模型，避免每条任务重新加载 base 权重（长视频尤其明显）。"""
    global _WHISPER_MODEL
    with _WHISPER_LOCK:
        if _WHISPER_MODEL is None:
            from faster_whisper import WhisperModel  # type: ignore

            _patch_av_open_compat()
            _WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8")
        return _WHISPER_MODEL


def _transcribe(video: Path, on_progress: Any = None) -> dict[str, Any]:
    """优先 Faster-Whisper；没有则返回空字幕骨架，仍可人工审/启发式。

    on_progress(meta)：阶段/百分比回调。长视频转写会跑数分钟，必须推进进度，不能钉死 40%。
    """
    def _emit(**meta: Any) -> None:
        if on_progress:
            try:
                on_progress(meta)
            except Exception:
                pass

    try:
        from faster_whisper import WhisperModel  # noqa: F401
    except Exception:
        _emit(stage="transcribing", percent=65, detail="未装 faster-whisper，已跳过")
        return {
            "engine": "none",
            "warning": "未安装 faster-whisper，已跳过自动字幕；可手动审或稍后安装",
            "segments": [],
            "text": "",
        }

    duration = _probe_duration_sec(video)
    dur_label = _fmt_hms(duration) if duration else "未知时长"
    _emit(stage="extract_audio", percent=42, detail=f"抽音轨中 · 视频 {dur_label}")

    # 先用 ffmpeg 抽 16k mono wav，绕开部分损坏容器；失败则直接喂原视频
    wav = video.with_suffix(".whisper16k.wav")
    audio_path = video
    try:
        from app.services.media_clip import resolve_ffmpeg

        ff = resolve_ffmpeg()
        if ff:
            # 按时长放宽超时：约 2× 实时 + 3 分钟底；最长 30 分钟
            extract_timeout = 1800
            if duration:
                extract_timeout = min(1800, max(300, int(duration * 2) + 180))
            subprocess.run(
                [
                    ff,
                    "-y",
                    "-i",
                    str(video),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-f",
                    "wav",
                    str(wav),
                ],
                check=True,
                capture_output=True,
                timeout=extract_timeout,
            )
            if wav.exists() and wav.stat().st_size > 44:
                audio_path = wav
    except Exception:
        audio_path = video

    _emit(stage="load_model", percent=48, detail="加载语音模型…")
    model = _get_whisper_model()
    _emit(
        stage="transcribing",
        percent=50,
        detail=f"转写中 00:00 / {dur_label}" if duration else "转写中…",
    )

    segments_out: list[dict[str, Any]] = []
    texts: list[str] = []
    last_emit = 0.0
    try:
        # beam_size=1 + 不依赖上文：CPU 上对 20+ 分钟片明显更快，健身房口播够用
        segs, info = model.transcribe(
            str(audio_path),
            language="zh",
            vad_filter=True,
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
        )
        total = float(getattr(info, "duration", 0) or 0) or (duration or 0.0)
        for s in segs:
            row = {
                "start": round(float(s.start), 2),
                "end": round(float(s.end), 2),
                "text": (s.text or "").strip(),
            }
            if row["text"]:
                segments_out.append(row)
                texts.append(row["text"])
            now = time.monotonic()
            if now - last_emit < 1.2:
                continue
            last_emit = now
            end_t = float(s.end or 0)
            if total > 0:
                ratio = max(0.0, min(1.0, end_t / total))
                pct = 50 + int(ratio * 22)  # 50→72
                _emit(
                    stage="transcribing",
                    percent=pct,
                    detail=f"转写中 {_fmt_hms(end_t)} / {_fmt_hms(total)} · 已 {len(segments_out)} 句",
                    size=f"{len(segments_out)} 句",
                )
            else:
                _emit(
                    stage="transcribing",
                    percent=min(70, 50 + len(segments_out) // 4),
                    detail=f"转写中 · 已 {len(segments_out)} 句",
                    size=f"{len(segments_out)} 句",
                )
    finally:
        if wav.exists():
            try:
                wav.unlink()
            except OSError:
                pass
    _emit(
        stage="transcribing",
        percent=72,
        detail=f"转写完成 · {len(segments_out)} 句",
        size=f"{len(segments_out)} 句",
    )
    return {"engine": "faster-whisper", "segments": segments_out, "text": "\n".join(texts)}


def _muscle_from_hit(hit: dict[str, Any] | None) -> str:
    """只用动作库字段；无命中则占位「全身」，由人工改。"""
    if not hit:
        return "全身"
    m = str(hit.get("muscle") or "").strip()
    return m if m in _KNOWN_MUSCLES else "全身"


def _fmt_mmss(sec: float) -> str:
    s = max(0, int(sec))
    return f"{s // 60:02d}:{s % 60:02d}"


def _run_coro(coro: Any) -> Any:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 已在事件循环里（少见）：开新线程跑
    out: dict[str, Any] = {}
    err: list[BaseException] = []

    def _runner() -> None:
        try:
            out["v"] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001
            err.append(e)

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if err:
        raise err[0]
    return out.get("v")


_STUDIO_PARSE_SYSTEM = """你是健身房跟练视频拆课助手。根据带时间戳的口播字幕，抽出训练动作清单。
规则：
1. 开场热身动作照抽，role=warmup，target_sets/target_reps 可 null；跳过寒暄、纯闲聊和收尾放松拉伸（口头叮嘱可忽略，有具体动作名的拉伸/激活要抽）。
2. spoken_name 用教练口中的标准动作名（如「高位下拉」「杠铃划船」），不要「上背部拉伸」这类含糊说法；看不清就写口语原词。
3. target_muscle 只能是：胸/背/肩/腿/臂/核心。
4. role：main / assist / isolation / warmup。
5. spoken_at = 正式讲/做该动作时的字幕秒数（报组次、讲要领、说「下一个/开始做」附近），不是示范画面逐帧起点。
   - 禁止用片头「今天做哪些动作」报菜单的时间；同一动作名出现多次时，取正式训练段那一次。
6. cues / mistakes 各 0～3 条，必须来自字幕里的要领/易错，并带 source_at（对应字幕秒数）；没有就空数组，禁止编造。
7. tempo / intensity 有则摘一句，无则空字符串。
8. 组次未提及时 target_sets/target_reps 置 null；热身尤其不要瞎填组次。
9. 若下面给了「可对照动作名表」：字幕里的说法能对上表里某个标准名时（同音字、平翘舌听错也算对上），spoken_name 照抄表内标准名；对不上才写口语原词，禁止编一个库里没有的动作名。
10. 混练视频按部位/阶段分块：每个 block 对应一段连续的训练内容（如 热身 / 胸日 / 背日）；单一部位视频可把热身单独一块或放在同块最前。
11. 片头仅报菜名、没有进入该动作教学的，不要单独抽成一条；等真正讲到再抽。
只输出 JSON：
{
  "plan_title": "短标题",
  "blocks": [
    {
      "block_title": "如 拉日 / 背",
      "target_muscle": "背",
      "exercises": [
        {
          "spoken_name": "高位下拉",
          "target_muscle": "背",
          "role": "main",
          "target_sets": 4,
          "target_reps": "8-10",
          "spoken_at": 72.5,
          "cues": [{"text":"肘往髋走","source_at":80}],
          "mistakes": [{"text":"别借力后仰","source_at":85}],
          "tempo": "",
          "intensity": ""
        }
      ]
    }
  ]
}"""

_PARSE_CHUNK_SECONDS = 300.0  # 5 分钟一块
_PARSE_CHUNK_OVERLAP = 30.0  # 块间重叠，避免跨块动作被切丢


def _build_name_vocabulary(session: Session) -> str:
    """从动作库按 coach_core 优先取常用动作名，作为 LLM 对照词表。"""
    try:
        rows = session.exec(
            select(Exercise).where(Exercise.name_zh.is_not(None)).order_by(Exercise.id)
        ).all()
    except Exception:
        return ""
    # 只取有效动作；coach_core 优先，每个部位各留一些常见名
    rows = [
        r for r in rows
        if getattr(r, "is_valid_exercise", True) and (r.name_zh or "").strip()
    ]
    core = [r.name_zh for r in rows if getattr(r, "coach_core", False)]
    rest = [r.name_zh for r in rows if not getattr(r, "coach_core", False)]
    names = core[:60] + rest[:40]
    names = [n for n in dict.fromkeys(names) if n]
    if not names:
        return ""
    return "可对照动作名表（能对上就照抄标准名）：\n" + "、".join(names)


def _chunk_segments(segments: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """按 5 分钟分块、块间留 30s 重叠；单块不超过 220 条字幕。"""
    if not segments:
        return []
    total_end = max(float(s.get("end") or s.get("start") or 0) for s in segments)
    if total_end <= _PARSE_CHUNK_SECONDS:
        return [segments]
    chunks: list[list[dict[str, Any]]] = []
    start = 0.0
    while start < total_end:
        end = start + _PARSE_CHUNK_SECONDS
        chunk = [
            s
            for s in segments
            if float(s.get("start") or 0) < end
            and float(s.get("end") or s.get("start") or 0) >= start - _PARSE_CHUNK_OVERLAP
        ]
        if chunk:
            chunks.append(chunk[:220])
        start = end - _PARSE_CHUNK_OVERLAP
    return chunks


def _format_segment_lines(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for seg in segments[:220]:
        text = str(seg.get("text") or "").strip()
        if text:
            lines.append(f"[{_fmt_mmss(float(seg.get('start') or 0))}] {text}")
    return "\n".join(lines)


def _normalize_llm_blocks(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """兼容新旧两种返回：blocks[] 优先；旧的单块结构包成一个 block。"""
    blocks_in = raw.get("blocks")
    if isinstance(blocks_in, list) and blocks_in:
        out: list[dict[str, Any]] = []
        for b in blocks_in:
            if isinstance(b, dict) and isinstance(b.get("exercises"), list):
                out.append(b)
        if out:
            return out
    exercises = raw.get("exercises")
    if isinstance(exercises, list) and exercises:
        return [
            {
                "block_title": str(raw.get("block_title") or "").strip(),
                "target_muscle": str(raw.get("target_muscle") or "").strip(),
                "exercises": exercises,
            }
        ]
    return []


def _llm_item_teach_score(item: dict[str, Any]) -> float:
    """合并去重时优先正式教学段：有要领/组次的、时间更靠后的加分。"""
    at = float(item.get("spoken_at") or 0)
    cues_n = 0
    for key in ("cues", "mistakes"):
        raw = item.get(key)
        if isinstance(raw, list):
            cues_n += len(raw)
    sets = item.get("target_sets")
    has_sets = 1 if (isinstance(sets, int) and sets > 0) or (isinstance(sets, str) and str(sets).isdigit()) else 0
    return cues_n * 100 + has_sets * 40 + at


def _merge_llm_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """多块结果按 (部位, 动作名) 合并去重；优先正式教学段（有要领/组次、时间更靠后）。"""
    merged: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], tuple[int, int]] = {}
    for block in blocks:
        muscle = str(block.get("target_muscle") or "").strip()
        title = str(block.get("block_title") or "").strip()
        exs = block.get("exercises") or []
        if not isinstance(exs, list) or not exs:
            continue
        bucket_idx: int | None = None
        for i, b in enumerate(merged):
            if b.get("target_muscle") == muscle and b.get("block_title") == title:
                bucket_idx = i
                break
        if bucket_idx is None:
            bucket_idx = len(merged)
            merged.append({"block_title": title, "target_muscle": muscle, "exercises": []})
        for item in exs:
            if not isinstance(item, dict):
                continue
            spoken = str(item.get("spoken_name") or "").strip()
            if not spoken:
                continue
            key = (muscle, canonicalize_exercise(spoken))
            if key in seen:
                bi, ei = seen[key]
                existing = merged[bi]["exercises"]
                if _llm_item_teach_score(item) > _llm_item_teach_score(existing[ei]):
                    existing[ei] = item
                continue
            seen[key] = (bucket_idx, len(merged[bucket_idx]["exercises"]))
            merged[bucket_idx]["exercises"].append(item)
    return [b for b in merged if b.get("exercises")]


def _llm_extract_plan(
    transcript: dict[str, Any],
    task: StudioTask,
    session: Session | None = None,
) -> dict[str, Any] | None:
    """DeepSeek（openai_compatible）拆课；分块调用 + 词表对照；失败或 mock 返回 None。"""
    from app.brain.llm import MockLLM, TEMPERATURE_STRUCTURED, get_llm

    llm = get_llm()
    if isinstance(llm, MockLLM):
        return None
    segments = list(transcript.get("segments") or [])
    if not segments and not transcript.get("text"):
        return None

    hint = ""
    if isinstance(task.draft_json, dict) and task.draft_json.get("plan_title"):
        hint = f"已知计划名倾向：{task.draft_json.get('plan_title')}\n"
    vocab = _build_name_vocabulary(session) if session is not None else ""

    def _call_chunk(chunk: list[dict[str, Any]]) -> dict[str, Any] | None:
        body = _format_segment_lines(chunk)
        if not body:
            body = str(transcript.get("text") or "")[:12000]
        if len(body) > 14000:
            body = body[:14000] + "\n…(字幕过长已截断)"
        parts = [
            f"{hint}视频模式：{task.mode}",
            "下面是 whisper 口播字幕（[mm:ss] 原文）。请拆出正式动作：",
            "",
            body,
        ]
        if vocab:
            parts += ["", vocab]
        user = "\n".join(parts)
        try:
            raw = _run_coro(
                llm.complete_json(_STUDIO_PARSE_SYSTEM, user, temperature=TEMPERATURE_STRUCTURED)
            )
        except Exception:
            return None
        return raw if isinstance(raw, dict) else None

    chunks = _chunk_segments(segments)
    if chunks:
        raw_blocks: list[dict[str, Any]] = []
        plan_title = ""
        for chunk in chunks:
            raw = _call_chunk(chunk)
            if not raw:
                continue
            if not plan_title:
                plan_title = str(raw.get("plan_title") or "").strip()
            raw_blocks.extend(_normalize_llm_blocks(raw))
        blocks = _merge_llm_blocks(raw_blocks)
        if blocks:
            return {"plan_title": plan_title, "blocks": blocks}
        return None

    # 无时间戳字幕：整段喂一次，兼容旧结构
    raw = _call_chunk(segments)
    if not raw:
        return None
    blocks = _merge_llm_blocks(_normalize_llm_blocks(raw))
    if blocks:
        return {"plan_title": str(raw.get("plan_title") or "").strip(), "blocks": blocks}
    return None


def _finalize_exercise_traffic(exercises: list[dict[str, Any]]) -> None:
    """灯色与百分制对齐：≥90 预填可绿/黄；有候选未绑=黄；无候选=红。

    热身 role=warmup 不填默认 3×8-12，避免看起来像正式组。
    """
    for ex in exercises:
        role = str(ex.get("role") or "")
        if ex.get("target_sets") is None and role != "warmup":
            ex["target_sets"] = 3
            ex["target_reps"] = ex.get("target_reps") or "8-12"
            ex["sets_from_transcript"] = False
        score = int(ex.get("match_score") or round(float(ex.get("match_confidence") or 0) * 100))
        ex["match_score"] = score
        ex["match_confidence"] = score / 100.0
        if not ex.get("cue_mode"):
            ex["cue_mode"] = "replace"  # 方案 A：默认按上面的换；真正写库在抽屉点按钮
        # 12 §3.1：有 exercise_id 即绿（点选即绑）；黄=有候选未点；红=无候选
        if ex.get("exercise_id"):
            ex["traffic"] = "green"
        elif ex.get("candidates") and score >= 55:
            ex["traffic"] = "amber"
        else:
            ex["traffic"] = "red"


def _build_draft(
    task: StudioTask,
    blocks_in: list[dict[str, Any]],
    *,
    title: str | None,
    parse_engine: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """blocks_in: [{block_title, target_muscle, exercises:[row...]}]；动作行已构造好。"""
    exercise_rows: list[dict[str, Any]] = []
    out_blocks: list[dict[str, Any]] = []
    for block in blocks_in:
        exs = list(block.get("exercises") or [])
        if not exs:
            continue
        muscle = str(block.get("target_muscle") or "").strip()
        if muscle not in _KNOWN_MUSCLES:
            muscle = (exs[0].get("target_muscle") if exs else None) or "全身"
        if muscle not in _KNOWN_MUSCLES:
            muscle = "全身"
        block_title = str(block.get("block_title") or "").strip() or {
            "胸": "推日 / 胸",
            "背": "拉日 / 背",
            "肩": "肩部",
            "腿": "腿日",
            "臂": "手臂",
            "核心": "核心",
            "全身": "待定部位",
        }.get(muscle, muscle)
        exercise_rows.extend(exs)
        out_blocks.append(
            {
                "title": block_title,
                "muscles": [muscle] if muscle != "全身" else [],
                "exercises": exs,
            }
        )
    _keep_snippets_on_own_action(exercise_rows)
    _finalize_exercise_traffic(exercise_rows)
    kept_title = None
    if isinstance(task.draft_json, dict):
        kept_title = task.draft_json.get("plan_title")
    title = title or kept_title
    if not title:
        muscle0 = out_blocks[0]["muscles"][0] if out_blocks and out_blocks[0]["muscles"] else "全身"
        title = f"工坊草稿 · {muscle0}" if task.mode != "exercise_only" else "动作素材草稿"
    if not out_blocks:
        out_blocks = [
            {
                "title": "待定部位",
                "muscles": [],
                "exercises": [],
            }
        ]
    draft = {
        "plan_title": title,
        "scene_tag": "博主同款" if task.mode != "exercise_only" else None,
        "mode": task.mode,
        "parse_engine": parse_engine,
        "blocks": out_blocks,
    }
    score = {
        "red_count": sum(1 for e in exercise_rows if e.get("traffic") == "red"),
        "amber_count": sum(1 for e in exercise_rows if e.get("traffic") == "amber"),
        "green_count": sum(1 for e in exercise_rows if e.get("traffic") == "green"),
        "total": len(exercise_rows),
        "parse_engine": parse_engine,
    }
    return draft, score


def _parse_and_score(
    session: Session, task: StudioTask, transcript: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    text = str(transcript.get("text") or "")
    segments = list(transcript.get("segments") or [])
    ensure_loaded()

    def _row_from_item(item: dict[str, Any], seq: int) -> dict[str, Any] | None:
        raw_spoken = str(item.get("spoken_name") or "").strip()
        if not raw_spoken:
            return None
        # 字幕错字（载剧下拉）先改成库里唯一的标准名，再匹配；定位仍可用原词
        repaired = repair_spoken_name(session, raw_spoken)
        spoken = repaired or raw_spoken
        spoken_at = float(item.get("spoken_at") or 0)
        snip = {
            "start": round(spoken_at, 2),
            "end": round(spoken_at + 5.0, 2),
            "spoken_at": round(spoken_at, 2),
        }
        # 字幕对齐优先取「正式教学段」命中，避免片头报菜名锁死在 00:00
        aligned = _snippet_for_name(segments, spoken) if segments else None
        if not aligned and spoken != raw_spoken:
            aligned = _snippet_for_name(segments, raw_spoken)
        if aligned:
            snip = aligned
            spoken_at = float(aligned.get("spoken_at") or spoken_at)
        muscle_hint = str(item.get("target_muscle") or "").strip() or None
        matched = _match_exercise(session, spoken, muscle_hint=muscle_hint if muscle_hint in _KNOWN_MUSCLES else None)
        hit = matched.get("hit")
        role = str(item.get("role") or "main")
        if role not in ("main", "assist", "isolation", "warmup"):
            role = "main"
        row = _exercise_draft_row(
            i=seq,
            spoken=spoken,
            hit=hit,
            snip=snip,
            segments=segments,
            role=role,
            attach_demo=not bool(hit and hit.get("has_demo")),
            source_kind="spoken",
            candidates=list(matched.get("candidates") or []),
            match_score=int(matched.get("match_score") or 0),
        )
        muscle = str(item.get("target_muscle") or "").strip()
        if muscle in _KNOWN_MUSCLES:
            row["target_muscle"] = muscle
        elif hit:
            row["target_muscle"] = _muscle_from_hit(hit)
        sets = item.get("target_sets")
        reps = item.get("target_reps")
        if isinstance(sets, int) and sets > 0:
            row["target_sets"] = sets
            row["target_reps"] = str(reps).strip() if reps else row.get("target_reps")
            row["sets_from_transcript"] = True
        elif isinstance(sets, str) and sets.isdigit():
            row["target_sets"] = int(sets)
            row["target_reps"] = str(reps).strip() if reps else row.get("target_reps")
            row["sets_from_transcript"] = True
        cues_in = item.get("cues") if isinstance(item.get("cues"), list) else []
        mistakes_in = item.get("mistakes") if isinstance(item.get("mistakes"), list) else []
        cues: list[dict[str, Any]] = []
        for c in cues_in[:3]:
            if isinstance(c, dict) and str(c.get("text") or "").strip():
                cues.append(
                    {
                        "text": str(c.get("text")).strip()[:80],
                        "source_at": float(c.get("source_at") or spoken_at),
                    }
                )
            elif isinstance(c, str) and c.strip():
                cues.append({"text": c.strip()[:80], "source_at": spoken_at})
        mistakes: list[dict[str, Any]] = []
        for c in mistakes_in[:3]:
            if isinstance(c, dict) and str(c.get("text") or "").strip():
                mistakes.append(
                    {
                        "text": str(c.get("text")).strip()[:80],
                        "source_at": float(c.get("source_at") or spoken_at),
                    }
                )
            elif isinstance(c, str) and c.strip():
                mistakes.append({"text": c.strip()[:80], "source_at": spoken_at})
        if cues:
            row["cues"] = cues
        if mistakes:
            row["mistakes"] = mistakes
        row["tempo"] = str(item.get("tempo") or "")[:60]
        row["intensity"] = str(item.get("intensity") or "")[:60]
        return row

    # 1) DeepSeek / 兼容 LLM（分块 + 词表 + 多块结构）
    llm_raw = _llm_extract_plan(transcript, task, session)
    if llm_raw:
        out_blocks: list[dict[str, Any]] = []
        seq = 0
        for block in llm_raw.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            rows: list[dict[str, Any]] = []
            for item in block.get("exercises") or []:
                if not isinstance(item, dict):
                    continue
                row = _row_from_item(item, seq)
                if row:
                    rows.append(row)
                    seq += 1
            if rows:
                out_blocks.append(
                    {
                        "block_title": str(block.get("block_title") or "").strip(),
                        "target_muscle": str(block.get("target_muscle") or "").strip(),
                        "exercises": rows,
                    }
                )
        if out_blocks:
            return _build_draft(
                task,
                out_blocks,
                title=str(llm_raw.get("plan_title") or "").strip() or None,
                parse_engine="llm",
            )

    # 2) 启发式兜底（目录子串 / 第N个动作）
    exercises = []
    mentions = find_catalog_mentions_in_text(text) if text else []
    if mentions:
        for i, name in enumerate(mentions[:12]):
            snip = _snippet_for_name(segments, name) or {
                "start": 10.0 * i,
                "end": 10.0 * i + 5,
                "spoken_at": 10.0 * i,
            }
            matched = _match_exercise(session, name)
            hit = matched.get("hit")
            exercises.append(
                _exercise_draft_row(
                    i=i,
                    spoken=name,
                    hit=hit,
                    snip=snip,
                    segments=segments,
                    role="main" if i < 2 else ("assist" if i < 4 else "isolation"),
                    attach_demo=not bool(hit and hit.get("has_demo")),
                    candidates=list(matched.get("candidates") or []),
                    match_score=int(matched.get("match_score") or 0),
                )
            )
    elif text:
        parts = re.split(r"(?:第[一二三四五六七八九十\d]+个动作|下一个动作|正式组)", text)
        for i, part in enumerate(parts[1:7], start=0):
            spoken = (part.strip()[:40] or f"未识别动作{i+1}")
            fallback = {"start": 10.0 * i, "end": 10.0 * i + 5, "spoken_at": 10.0 * i}
            snip = (_snippet_for_name(segments, spoken[:6]) if segments else None) or fallback
            exercises.append(
                _exercise_draft_row(
                    i=i,
                    spoken=spoken,
                    hit=None,
                    snip=snip,
                    segments=segments,
                    role="main" if i == 0 else "assist",
                    attach_demo=True,
                    conf=0.1,
                )
            )

    sets_match = _SETS_RE.search(text) if text else None
    for ex in exercises:
        if sets_match and not ex.get("sets_from_transcript"):
            ex["target_sets"] = int(sets_match.group("sets"))
            if sets_match.group("reps_a") and sets_match.group("reps_b"):
                ex["target_reps"] = f"{sets_match.group('reps_a')}-{sets_match.group('reps_b')}"
            elif sets_match.group("reps"):
                ex["target_reps"] = str(sets_match.group("reps"))
            ex["sets_from_transcript"] = True

    return _build_draft(
        task,
        [{"block_title": "", "target_muscle": "", "exercises": exercises}],
        title=None,
        parse_engine="heuristic",
    )


def _nearby_lines(
    segments: list[dict[str, Any]], spoken_at: float, *, window: float = 12.0
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for seg in segments:
        s = float(seg.get("start") or 0)
        if abs(s - spoken_at) <= window:
            out.append(
                {
                    "text": str(seg.get("text") or "").strip(),
                    "at": round(s, 2),
                }
            )
    return out[:4]


def _exercise_draft_row(
    *,
    i: int,
    spoken: str,
    hit: dict[str, Any] | None,
    snip: dict[str, float],
    segments: list[dict[str, Any]],
    role: str,
    attach_demo: bool,
    conf: float | None = None,
    source_kind: str = "spoken",
    candidates: list[dict[str, Any]] | None = None,
    match_score: int | None = None,
) -> dict[str, Any]:
    score = int(
        match_score
        if match_score is not None
        else (hit.get("score") if hit and hit.get("score") is not None else round(float(conf if conf is not None else (hit["confidence"] if hit else 0.0)) * 100))
    )
    confidence = score / 100.0
    spoken_at = float(snip.get("spoken_at") or snip.get("start") or 0)
    nearby = _nearby_lines(segments, spoken_at)
    cues = [
        {"text": n["text"], "source_at": n["at"]}
        for n in nearby
        if any(k in n["text"] for k in ("注意", "不要", "别", "保持", "感受", "顶住", "下放"))
    ][:2]
    mistakes = [
        {"text": n["text"], "source_at": n["at"]}
        for n in nearby
        if any(k in n["text"] for k in ("别", "不要", "错误", "避免", "翻", "打开太多"))
    ][:2]
    media_status = "library" if hit and hit.get("has_demo") else ("pending_sku" if not hit else "uncut")
    cands = list(candidates or [])
    return {
        "id": f"row-{i}",
        "spoken_name": spoken,
        "exercise_id": hit["id"] if hit else None,
        "exercise_name": hit["name_zh"] if hit else (None if source_kind == "missing" else spoken),
        "target_muscle": _muscle_from_hit(hit),
        "gear": hit.get("gear") if hit else None,
        "role": role,
        "target_sets": None,
        "target_reps": None,
        "sets_from_transcript": False,
        "source_kind": source_kind,
        "match_score": score,
        "match_confidence": confidence,
        "candidates": cands,
        "snippet": {
            "start": float(snip.get("start") or 0),
            "end": float(snip.get("end") or 5),
            "spoken_at": spoken_at,
        },
        "spoken_at": spoken_at,
        "media_status": media_status,
        "cues": cues,
        "mistakes": mistakes,
        "tempo": "",
        "intensity": "",
        "traffic": "red",
        "replace_demo": False,
        "attach_demo": attach_demo,
        "cue_mode": "replace",
        "cues_library_backup": None,
        "cue_pairs": None,
    }


_TEACH_HINTS = ("组", "次", "注意", "不要", "别", "感受", "保持", "开始", "来做", "要领")
_INTRO_HINTS = ("今天", "安排", "几个动作", "分别是", "包括", "计划", "一共", "先说", "介绍")
_NEXT_ACTION = re.compile(r"第[一二三四五六七八九十\d]+个动作|下一个动作|收尾动作|首先先做")
_SNIPPET_MAX_SEC = 8.0


def _snippet_for_name(segments: list[dict[str, Any]], name: str) -> dict[str, float] | None:
    """在字幕里找动作名。选区从这一句开口起往后续讲，不往前倒进上一个动作。"""
    key = (name or "").strip()
    if len(key) < 2:
        return None

    hits: list[tuple[float, int, float]] = []
    for i, seg in enumerate(segments):
        text = str(seg.get("text") or "")
        if key not in text:
            continue
        start = float(seg.get("start") or 0)
        near = " ".join(
            str(segments[j].get("text") or "")
            for j in range(max(0, i - 1), min(len(segments), i + 3))
        )
        score = start / 1000.0  # 同质量时略偏后段
        if any(k in near for k in _TEACH_HINTS):
            score += 12
        if any(k in near for k in _INTRO_HINTS):
            score -= 8
        if ("、" in text or "，" in text) and not any(k in near for k in _TEACH_HINTS):
            score -= 4
        hits.append((score, i, start))

    if not hits:
        return None
    hits.sort(key=lambda x: x[0], reverse=True)
    _score, idx, start = hits[0]
    end_limit = start + _SNIPPET_MAX_SEC
    end = float(segments[idx].get("end") or (start + 4))
    for j in range(idx + 1, len(segments)):
        text = str(segments[j].get("text") or "")
        st = float(segments[j].get("start") or 0)
        if st >= end_limit or _NEXT_ACTION.search(text):
            break
        end = float(segments[j].get("end") or (st + 1))
    if end < start + 3:
        end = min(end_limit, start + 4)
    return {
        "start": round(max(0, start), 2),
        "end": round(end, 2),
        "spoken_at": round(start, 2),
    }


def _keep_snippets_on_own_action(rows: list[dict[str, Any]]) -> None:
    """选区不得早于本动作开口，也不得盖住下一条的开口。"""
    ordered = sorted(rows, key=lambda r: float(r.get("spoken_at") or 0))
    for i, row in enumerate(ordered):
        at = float(row.get("spoken_at") or 0)
        snip = dict(row.get("snippet") or {})
        start = max(float(snip.get("start") or at), at)
        end = float(snip.get("end") or (start + 5))
        nxt = float(ordered[i + 1].get("spoken_at") or 0) if i + 1 < len(ordered) else None
        if nxt and nxt > start:
            end = min(end, nxt - 0.1)
        if end < start + 2.5:
            end = start + 2.5
            if nxt and nxt > start:
                end = min(end, nxt - 0.05)
        if end <= start:
            end = start + 2.5
        row["snippet"] = {
            "start": round(start, 2),
            "end": round(end, 2),
            "spoken_at": round(at, 2),
        }
        row["spoken_at"] = round(at, 2)


def _match_exercise(
    session: Session,
    spoken: str,
    *,
    muscle_hint: str | None = None,
) -> dict[str, Any]:
    """百分制候选匹配。返回 {hit, candidates, match_score, ambiguous}。

    含糊口播不自动绑；≥90 才预填 hit。旧调用只取 hit 时用 .get("hit")。
    """
    return resolve_spoken_match(session, spoken, muscle_hint=muscle_hint, limit=3)


def preview_clip(
    session: Session, *, task_id: int, start: float, end: float
) -> dict[str, Any]:
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    video = _abs_video(task)
    if not video or not video.exists():
        raise HTTPException(status_code=400, detail="任务还没有可切片的视频")
    if end <= start:
        raise HTTPException(status_code=400, detail="结束时间必须大于开始时间")
    if not ffmpeg_available():
        raise HTTPException(status_code=400, detail="未安装 ffmpeg")

    tmp = _task_dir(task_id) / "preview"
    mp4, jpg = make_demo_pair(video, start=start, end=end, out_dir=tmp, stem="preview")
    mp4_bytes = mp4.read_bytes()
    jpg_bytes = jpg.read_bytes()
    demo_url = save_public_asset(mp4_bytes, f"studio/{task_id}/preview_loop.mp4", "video/mp4")
    cover_url = save_public_asset(jpg_bytes, f"studio/{task_id}/preview_cover.jpg", "image/jpeg")
    return {"demo_url": demo_url, "cover_url": cover_url, "start": start, "end": end}


def quick_create_exercise(
    session: Session,
    *,
    task_id: int,
    spoken_name: str,
    muscle: str,
    gear: str = "器械",
    role: str = "isolation",
    start: float | None = None,
    end: float | None = None,
    attach_demo: bool = True,
    cues: list[Any] | None = None,
    mistakes: list[Any] | None = None,
    instructions: list[Any] | None = None,
    write_cues: bool = False,
) -> dict[str, Any]:
    from app.services import admin_editor

    name = (spoken_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="动作名不能为空")
    payload: dict[str, Any] = {
        "name_zh": name,
        "muscle": muscle or "全身",
        "gear": gear or "器械",
        "modality": "抗阻" if role != "warmup" else "灵活性",
        "aliases": [name],
        "coach_core": False,
        "needs_review": False,
    }
    # 新建时可顺带写入要领；默认仍不写（仅本次），由 write_cues / 发布时 cue_mode 决定
    if write_cues:
        cue_texts = _line_texts(cues)
        mistake_texts = _line_texts(mistakes)
        instr = _line_texts(instructions) or cue_texts[:4]
        if cue_texts:
            payload["cues_zh"] = cue_texts
        if mistake_texts:
            payload["common_mistakes_zh"] = mistake_texts
        if instr:
            payload["instructions_zh"] = instr
    created = admin_editor.create_exercise(session, payload)
    ex_id = created["id"]
    # 槽位角色
    ex = session.get(Exercise, ex_id)
    if ex:
        ex.slot_roles = [role] if role else ["isolation"]
        session.add(ex)
        session.commit()

    demo_meta = None
    task = session.get(StudioTask, task_id)
    if attach_demo and task and start is not None and end is not None:
        demo_meta = _attach_demo_media(session, task, ex_id, float(start), float(end))

    return {"exercise": created, "demo": demo_meta}


def _attach_demo_media(
    session: Session, task: StudioTask, exercise_id: str, start: float, end: float
) -> dict[str, Any] | None:
    video = _abs_video(task)
    if not video or not video.exists() or not ffmpeg_available():
        return None
    tmp = _task_dir(task.id or 0) / f"demo_{exercise_id}"
    mp4, jpg = make_demo_pair(video, start=start, end=end, out_dir=tmp, stem=exercise_id)
    demo_url = save_public_asset(mp4.read_bytes(), f"exercises/custom/{exercise_id}_demo.mp4", "video/mp4")
    cover_url = save_public_asset(jpg.read_bytes(), f"exercises/custom/{exercise_id}_start.jpg", "image/jpeg")

    # 撤旧 published demo
    old = session.exec(
        select(ExerciseMedia).where(
            ExerciseMedia.exercise_id == exercise_id,
            ExerciseMedia.role == "demo",
            ExerciseMedia.status == "published",
        )
    ).all()
    for row in old:
        row.status = "archived"
        session.add(row)

    media = ExerciseMedia(
        exercise_id=exercise_id,
        role="demo",
        url=demo_url,
        status="published",
        source="video_studio",
        meta={"mime": "video/mp4", "start": start, "end": end},
    )
    session.add(media)

    # 封面：始终刷新 published start + image_start（示范与列表缩略图同源）
    old_starts = session.exec(
        select(ExerciseMedia).where(
            ExerciseMedia.exercise_id == exercise_id,
            ExerciseMedia.role == "start",
            ExerciseMedia.status == "published",
        )
    ).all()
    for row in old_starts:
        row.status = "archived"
        session.add(row)
    session.add(
        ExerciseMedia(
            exercise_id=exercise_id,
            role="start",
            url=cover_url,
            status="published",
            source="video_studio",
            meta={"mime": "image/jpeg"},
        )
    )

    ex = session.get(Exercise, exercise_id)
    if ex:
        ex.image_start = cover_url
        ex.updated_at = utcnow()
        session.add(ex)
    # 示范只写媒体；要领走抽屉写入
    session.commit()
    return {"demo_url": demo_url, "cover_url": cover_url}


def _draft_row_for_exercise(task: StudioTask, exercise_id: str) -> dict[str, Any] | None:
    draft = task.draft_json if isinstance(task.draft_json, dict) else {}
    for block in draft.get("blocks") or []:
        for ex in block.get("exercises") or []:
            if not isinstance(ex, dict):
                continue
            if str(ex.get("exercise_id") or "") == str(exercise_id):
                return ex
    return None


def _line_texts(items: Any, *, limit: int = 6) -> list[str]:
    out: list[str] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(item or "").strip()
        if text and text not in out:
            out.append(text[:120])
        if len(out) >= limit:
            break
    return out


def _merge_unique(old: list[Any], new: list[str], *, limit: int = 8) -> list[str]:
    out: list[str] = []
    for x in list(old or []) + list(new or []):
        t = str(x or "").strip()
        if t and t not in out:
            out.append(t[:120])
        if len(out) >= limit:
            break
    return out


def _sync_sku_text_from_draft(
    session: Session,
    task: StudioTask,
    exercise_id: str,
    *,
    mode: str = "replace",
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按 cue_mode 把草稿要领写入动作库。

    - none：不动库
    - append：去重合并
    - replace：先把旧值备份进草稿 cues_library_backup，再覆盖
    """
    mode = (mode or "none").strip().lower()
    if mode not in ("append", "replace"):
        return {"ok": False, "reason": "cue_mode_none"}
    draft_row = row or _draft_row_for_exercise(task, exercise_id)
    ex = session.get(Exercise, exercise_id)
    if not draft_row or not ex:
        return {"ok": False, "reason": "no_draft_row"}

    cues = _line_texts(draft_row.get("cues"))
    mistakes = _line_texts(draft_row.get("mistakes"))
    if not cues and not mistakes:
        return {"ok": False, "reason": "empty_cues"}

    backup = {
        "cues_zh": list(ex.cues_zh or []),
        "common_mistakes_zh": list(ex.common_mistakes_zh or []),
        "instructions_zh": list(ex.instructions_zh or []),
    }
    if mode == "replace":
        draft_row["cues_library_backup"] = backup
        if cues:
            ex.cues_zh = cues
            ex.instructions_zh = cues[:4] if not (ex.instructions_zh or []) else list(ex.instructions_zh or [])
            # 替换模式下教案也跟视频版走（有 cues 时）
            ex.instructions_zh = cues[:4]
        if mistakes:
            ex.common_mistakes_zh = mistakes
    else:  # append
        if cues:
            ex.cues_zh = _merge_unique(ex.cues_zh or [], cues)
            if not (ex.instructions_zh or []):
                ex.instructions_zh = cues[:4]
            else:
                ex.instructions_zh = _merge_unique(ex.instructions_zh or [], cues, limit=8)
        if mistakes:
            ex.common_mistakes_zh = _merge_unique(ex.common_mistakes_zh or [], mistakes)

    ex.updated_at = utcnow()
    session.add(ex)
    return {
        "ok": True,
        "mode": mode,
        "cues": list(ex.cues_zh or []),
        "mistakes": list(ex.common_mistakes_zh or []),
        "instructions": list(ex.instructions_zh or [])[:4],
        "backup": backup if mode == "replace" else None,
    }


def restore_sku_cues_from_backup(
    session: Session, *, task_id: int, exercise_id: str
) -> dict[str, Any]:
    """保留后端能力；产品方案 A 不做还原入口，前端勿调用。"""
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    row = _draft_row_for_exercise(task, exercise_id)
    ex = session.get(Exercise, exercise_id)
    if not row or not ex:
        raise HTTPException(status_code=404, detail="动作或草稿行不存在")
    backup = row.get("cues_library_backup")
    if not isinstance(backup, dict):
        raise HTTPException(status_code=400, detail="没有可还原的备份（需先做过替换写库）")
    ex.cues_zh = list(backup.get("cues_zh") or [])
    ex.common_mistakes_zh = list(backup.get("common_mistakes_zh") or [])
    ex.instructions_zh = list(backup.get("instructions_zh") or [])
    ex.updated_at = utcnow()
    session.add(ex)
    session.commit()
    return {"ok": True, "exercise_id": exercise_id, "restored": backup}


_CUE_PAIR_SYSTEM = """你是健身教案编辑。把「库内要领」与「本次视频抽出的要领」逐条配对。
规则：
1. 同一要点用 relation=replace，library_cue 填旧句、draft_cue 填视频句。
2. 库里没有的视频要点用 relation=add，library_cue=null。
3. 视频没提到、应保留的旧要点用 relation=keep，draft_cue=null。
4. 禁止编造原文没有的句子；reason 一句话。
只输出 JSON：
{"pairs":[{"library_cue":string|null,"draft_cue":string|null,"relation":"replace"|"add"|"keep","reason":string}],
 "summary":{"replace":n,"add":n,"keep":n,"result_total":n}}"""


def _aggregate_cues_draft(row: dict[str, Any]) -> list[dict[str, Any]]:
    """现网 cues + mistakes → 统一视图（不新建列）。"""
    out: list[dict[str, Any]] = []
    for kind, key in (("cue", "cues"), ("mistake", "mistakes")):
        for item in row.get(key) or []:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                out.append(
                    {
                        "text": text[:120],
                        "timestamp": item.get("source_at"),
                        "source_segment": item.get("source_at"),
                        "kind": kind,
                    }
                )
            elif str(item or "").strip():
                out.append(
                    {
                        "text": str(item).strip()[:120],
                        "timestamp": None,
                        "source_segment": None,
                        "kind": kind,
                    }
                )
    return out


def _fallback_cue_pairs(
    library: list[str], draft: list[str]
) -> dict[str, Any]:
    """配对失败：两列平铺，处理列待判断（前端可改 relation）。"""
    pairs: list[dict[str, Any]] = []
    for t in library:
        pairs.append(
            {
                "library_cue": t,
                "draft_cue": None,
                "relation": "keep",
                "reason": "待判断",
                "pending": True,
            }
        )
    for t in draft:
        pairs.append(
            {
                "library_cue": None,
                "draft_cue": t,
                "relation": "add",
                "reason": "待判断",
                "pending": True,
            }
        )
    return {
        "pairs": pairs,
        "summary": {
            "replace": 0,
            "add": len(draft),
            "keep": len(library),
            "result_total": len(library) + len(draft),
        },
        "degraded": True,
        "engine": "fallback",
    }


def pair_studio_cues(
    session: Session,
    *,
    task_id: int,
    row_id: str,
    exercise_id: str | None = None,
) -> dict[str, Any]:
    """LLM 逐条配对；超时 8s 或失败则降级人工表。"""
    import asyncio

    from app.brain.llm import MockLLM, TEMPERATURE_STRUCTURED, get_llm

    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    row = None
    for block in (task.draft_json or {}).get("blocks") or []:
        for ex in block.get("exercises") or []:
            if isinstance(ex, dict) and str(ex.get("id") or "") == str(row_id):
                row = ex
                break
        if row:
            break
    if not row:
        raise HTTPException(status_code=404, detail="草稿行不存在")

    eid = str(exercise_id or row.get("exercise_id") or "")
    ex = session.get(Exercise, eid) if eid else None
    library = [str(x).strip() for x in (ex.cues_zh or []) if str(x).strip()] if ex else []
    if ex:
        for x in ex.common_mistakes_zh or []:
            t = str(x).strip()
            if t and t not in library:
                library.append(t)
    draft_view = _aggregate_cues_draft(row)
    draft_texts = [d["text"] for d in draft_view]

    if not library and draft_texts:
        pairs = [
            {
                "library_cue": None,
                "draft_cue": t,
                "relation": "add",
                "reason": "库内为空，整表新增",
            }
            for t in draft_texts
        ]
        result = {
            "pairs": pairs,
            "summary": {
                "replace": 0,
                "add": len(pairs),
                "keep": 0,
                "result_total": len(pairs),
            },
            "degraded": False,
            "engine": "empty_library",
        }
    elif not draft_texts:
        result = _fallback_cue_pairs(library, [])
        result["engine"] = "empty_draft"
        result["degraded"] = False
    else:
        llm = get_llm()
        result = None
        if not isinstance(llm, MockLLM):
            user = (
                "库内要领：\n"
                + "\n".join(f"- {t}" for t in library)
                + "\n\n本次视频要领：\n"
                + "\n".join(f"- {t}" for t in draft_texts)
            )
            try:
                raw = _run_coro(
                    asyncio.wait_for(
                        llm.complete_json(
                            _CUE_PAIR_SYSTEM, user, temperature=TEMPERATURE_STRUCTURED
                        ),
                        timeout=8.0,
                    )
                )
                if isinstance(raw, dict) and isinstance(raw.get("pairs"), list):
                    pairs = []
                    for p in raw["pairs"]:
                        if not isinstance(p, dict):
                            continue
                        rel = str(p.get("relation") or "add").strip().lower()
                        if rel not in ("replace", "add", "keep"):
                            rel = "add"
                        pairs.append(
                            {
                                "library_cue": (str(p["library_cue"]).strip() if p.get("library_cue") else None),
                                "draft_cue": (str(p["draft_cue"]).strip() if p.get("draft_cue") else None),
                                "relation": rel,
                                "reason": str(p.get("reason") or "")[:80],
                            }
                        )
                    if pairs:
                        summary = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
                        result = {
                            "pairs": pairs,
                            "summary": {
                                "replace": int(summary.get("replace") or sum(1 for x in pairs if x["relation"] == "replace")),
                                "add": int(summary.get("add") or sum(1 for x in pairs if x["relation"] == "add")),
                                "keep": int(summary.get("keep") or sum(1 for x in pairs if x["relation"] == "keep")),
                                "result_total": int(
                                    summary.get("result_total")
                                    or sum(1 for x in pairs if x["relation"] in ("replace", "add", "keep"))
                                ),
                            },
                            "degraded": False,
                            "engine": "llm",
                        }
            except Exception:
                result = None
        if result is None:
            result = _fallback_cue_pairs(library, draft_texts)

    # 写回草稿行 cue_pairs
    draft = dict(task.draft_json or {})
    for block in draft.get("blocks") or []:
        for ex in block.get("exercises") or []:
            if isinstance(ex, dict) and str(ex.get("id") or "") == str(row_id):
                ex["cue_pairs"] = result
                break
    task.draft_json = draft
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    return {
        "ok": True,
        "row_id": row_id,
        "exercise_id": eid or None,
        "library": library,
        "draft": draft_view,
        **result,
    }


def write_studio_cues(
    session: Session,
    *,
    task_id: int,
    row_id: str,
    cue_mode: str = "replace",
    pairs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """抽屉「把要领写进库」：按配对结果 + cue_mode 落库。"""
    mode = (cue_mode or "replace").strip().lower()
    if mode == "none":
        return {"ok": False, "reason": "cue_mode_none", "message": "已选不入库"}
    if mode not in ("append", "replace"):
        raise HTTPException(status_code=400, detail="cue_mode 只能是 none/append/replace")

    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    row = None
    for block in (task.draft_json or {}).get("blocks") or []:
        for ex in block.get("exercises") or []:
            if isinstance(ex, dict) and str(ex.get("id") or "") == str(row_id):
                row = ex
                break
        if row:
            break
    if not row:
        raise HTTPException(status_code=404, detail="草稿行不存在")
    eid = str(row.get("exercise_id") or "")
    if not eid:
        raise HTTPException(status_code=400, detail="请先绑定动作再写要领")
    ex = session.get(Exercise, eid)
    if not ex:
        raise HTTPException(status_code=404, detail="动作不存在")

    pair_blob = pairs if isinstance(pairs, list) else None
    if pair_blob is None:
        stored = row.get("cue_pairs")
        if isinstance(stored, dict):
            pair_blob = list(stored.get("pairs") or [])
        elif isinstance(stored, list):
            pair_blob = stored
    if not pair_blob:
        # 无配对则退回旧同步逻辑
        synced = _sync_sku_text_from_draft(session, task, eid, mode=mode, row=row)
        if synced.get("backup"):
            row["cues_library_backup"] = {
                **synced["backup"],
                "replaced_at": utcnow().isoformat(),
                "source_task_id": task_id,
            }
        draft = dict(task.draft_json or {})
        task.draft_json = draft
        session.add(task)
        session.commit()
        return {"ok": bool(synced.get("ok")), **synced}

    backup = {
        "cues_zh": list(ex.cues_zh or []),
        "common_mistakes_zh": list(ex.common_mistakes_zh or []),
        "instructions_zh": list(ex.instructions_zh or []),
        "replaced_at": utcnow().isoformat(),
        "source_task_id": task_id,
    }

    if mode == "append":
        added = [
            str(p.get("draft_cue") or "").strip()
            for p in pair_blob
            if str(p.get("relation") or "") == "add" and p.get("draft_cue")
        ]
        ex.cues_zh = _merge_unique(ex.cues_zh or [], added)
        if added and not (ex.instructions_zh or []):
            ex.instructions_zh = added[:4]
    else:  # replace：按配对表换掉 + 追加新增；keep 保留
        next_cues: list[str] = []
        for p in pair_blob:
            rel = str(p.get("relation") or "").strip().lower()
            lib = str(p.get("library_cue") or "").strip()
            dr = str(p.get("draft_cue") or "").strip()
            if rel == "replace" and dr:
                if dr not in next_cues:
                    next_cues.append(dr[:120])
            elif rel == "keep" and lib:
                if lib not in next_cues:
                    next_cues.append(lib[:120])
            elif rel == "add" and dr:
                if dr not in next_cues:
                    next_cues.append(dr[:120])
        # 若配对里没 keep 旧项，仍保留未出现在 pairs 里的旧 cues？方案 A：只信配对表
        if next_cues:
            ex.cues_zh = next_cues[:8]
            ex.instructions_zh = next_cues[:4]
        row["cues_library_backup"] = backup

    # mistakes：视频 mistakes 在 append/replace 时合并或覆盖
    draft_mistakes = _line_texts(row.get("mistakes"))
    if draft_mistakes:
        if mode == "append":
            ex.common_mistakes_zh = _merge_unique(ex.common_mistakes_zh or [], draft_mistakes)
        else:
            ex.common_mistakes_zh = draft_mistakes[:8]

    ex.updated_at = utcnow()
    session.add(ex)
    row["cue_mode"] = mode
    draft = dict(task.draft_json or {})
    task.draft_json = draft
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    return {
        "ok": True,
        "mode": mode,
        "exercise_id": eid,
        "cues": list(ex.cues_zh or []),
        "mistakes": list(ex.common_mistakes_zh or []),
        "instructions": list(ex.instructions_zh or [])[:4],
        "backup": backup if mode == "replace" else None,
    }


async def upload_task_cover(session: Session, task_id: int, file: UploadFile) -> dict[str, Any]:
    """工坊草稿计划封面：本地上传 → save_public_asset → 写入 draft.cover_url。"""
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    filename = file.filename or "cover.bin"
    ext = Path(filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '(无扩展名)'}")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（上限 12MB）")

    from app.services.admin_plans import _process_landscape_cover

    payload, save_ext = _process_landscape_cover(raw)
    token = uuid.uuid4().hex[:8]
    url = save_public_asset(
        payload,
        f"studio/{task_id}/plan_cover_{token}{save_ext}",
        "image/jpeg" if save_ext == ".jpg" else "application/octet-stream",
    )
    draft = dict(task.draft_json or {})
    draft["cover_url"] = url
    task.draft_json = draft
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    return get_task(session, task_id)


def update_task_draft(session: Session, task_id: int, draft: dict[str, Any]) -> dict[str, Any]:
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    task.draft_json = draft
    # 重算红/黄/绿
    exercises = []
    for b in draft.get("blocks") or []:
        exercises.extend(b.get("exercises") or [])
    red = sum(1 for e in exercises if e.get("traffic") == "red" or not e.get("exercise_id"))
    amber = sum(1 for e in exercises if e.get("traffic") == "amber" and e.get("exercise_id"))
    green = sum(1 for e in exercises if e.get("traffic") == "green" and e.get("exercise_id"))
    task.score = {
        "red_count": red,
        "amber_count": amber,
        "green_count": green,
        "total": len(exercises),
    }
    task.review_state = "needs_review" if (red or amber) else "auto_pass"
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    return get_task(session, task_id)


def confirm_plan(
    session: Session,
    *,
    task_id: int,
    draft: dict[str, Any] | None = None,
    append_to_plan_id: str | None = None,
    publish: bool = True,
) -> dict[str, Any]:
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if draft:
        task.draft_json = draft
        session.add(task)
        session.commit()
        session.refresh(task)

    data = dict(task.draft_json or {})
    blocks_in = list(data.get("blocks") or [])
    if not blocks_in:
        raise HTTPException(status_code=400, detail="草稿没有板块")

    # 硬门禁：全部绑定 exercise_id
    for b in blocks_in:
        for ex in b.get("exercises") or []:
            if not ex.get("exercise_id"):
                raise HTTPException(
                    status_code=400,
                    detail=f"动作「{ex.get('spoken_name') or ex.get('exercise_name') or '?'}」未绑定 SKU，请先一键新建或搜库换绑",
                )

    # 方案 A：要领只在抽屉显式写入，发布不再批量同步
    # 仅存动作素材：不建计划，只把勾选的示范写入动作库
    mode = str(data.get("mode") or task.mode or "")
    if mode == "exercise_only":
        attached = 0
        for b in blocks_in:
            for ex in b.get("exercises") or []:
                if not (ex.get("attach_demo") or ex.get("replace_demo")):
                    continue
                snip = ex.get("snippet") or {}
                st = float(snip.get("start") or 0)
                en = float(snip.get("end") or (st + 5))
                _attach_demo_media(session, task, str(ex["exercise_id"]), st, en)
                attached += 1
        data["blocks"] = blocks_in
        task.draft_json = data
        task.result_ref = {"mode": "exercise_only", "attached": attached, "published": True}
        task.review_state = "published"
        task.updated_at = utcnow()
        session.add(task)
        session.commit()
        return {
            "ok": True,
            "plan_id": None,
            "block_ids": [],
            "attached": attached,
        }

    # 同 batch 合并：收集同 batch 其它 done 任务
    batch_tasks = [task]
    if task.batch_id and task.mode == "plan_merge":
        others = session.exec(
            select(StudioTask)
            .where(StudioTask.batch_id == task.batch_id)
            .where(StudioTask.status == "done")
            .order_by(col(StudioTask.batch_order), col(StudioTask.id))
        ).all()
        batch_tasks = list(others) or [task]
        # 用各任务自己的第一板块拼起来
        merged_blocks: list[dict[str, Any]] = []
        for t in batch_tasks:
            d = t.draft_json or {}
            for b in d.get("blocks") or []:
                merged_blocks.append(b)
        if merged_blocks:
            blocks_in = merged_blocks
            data["blocks"] = merged_blocks

    title = str(data.get("plan_title") or "工坊计划").strip()
    scene_tag = data.get("scene_tag")
    cover_url = (str(data.get("cover_url") or "").strip() or None)

    if append_to_plan_id:
        tpl = session.get(PlanTemplate, append_to_plan_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="要并入的计划不存在")
        plan_id = tpl.id
        if cover_url and not tpl.cover_url:
            tpl.cover_url = cover_url
            session.add(tpl)
        max_order = session.exec(
            select(PlanBlock).where(PlanBlock.template_id == plan_id)
        ).all()
        base_order = max((b.order_index for b in max_order), default=-1) + 1
    else:
        plan_id = f"studio-{uuid.uuid4().hex[:10]}"
        now = utcnow()
        tpl = PlanTemplate(
            id=plan_id,
            title=title,
            author="内容工坊",
            badge_label="工坊",
            template_type="fixed",
            scene_tag=scene_tag,
            cover_url=cover_url,
            days_per_week=max(1, len(blocks_in)),
            muscle_tags=sorted(
                {
                    str(m)
                    for b in blocks_in
                    for m in (b.get("muscles") or [])
                    if m
                }
            ),
            is_published=bool(publish),
            sort_order=0,
            created_at=now,
            updated_at=now,
        )
        session.add(tpl)
        session.flush()
        base_order = 0

    assert plan_id
    created_block_ids: list[int] = []
    for i, b in enumerate(blocks_in):
        block_cover = (str(b.get("cover_url") or "").strip() or None)
        block = PlanBlock(
            template_id=plan_id,
            order_index=base_order + i,
            title=str(b.get("title") or f"板块{i+1}"),
            muscles=list(b.get("muscles") or []),
            cover_url=block_cover,
            note=None,
        )
        session.add(block)
        session.flush()
        created_block_ids.append(int(block.id))
        for j, ex in enumerate(b.get("exercises") or []):
            snip = ex.get("snippet") or {}
            row = PlanExercise(
                block_id=block.id,
                order_index=j,
                exercise_id=ex.get("exercise_id"),
                exercise_name=ex.get("exercise_name") or ex.get("spoken_name"),
                role=ex.get("role") or "main",
                lock_level="fixed",
                target_sets=ex.get("target_sets"),
                target_reps=ex.get("target_reps"),
                warmup_sets=int(ex.get("warmup_sets") or 0),
                target_muscle=ex.get("target_muscle"),
                source_kind=ex.get("source_kind") or "spoken",
                match_confidence=ex.get("match_confidence"),
                source_snippet={
                    "task_id": task.id,
                    "start": snip.get("start"),
                    "end": snip.get("end"),
                },
            )
            session.add(row)
            # 勾选补/换示范
            if ex.get("attach_demo") or ex.get("replace_demo"):
                st = float(snip.get("start") or 0)
                en = float(snip.get("end") or (st + 5))
                if ex.get("exercise_id"):
                    _attach_demo_media(session, task, str(ex["exercise_id"]), st, en)

    if append_to_plan_id:
        tpl = session.get(PlanTemplate, plan_id)
        if tpl:
            tpl.updated_at = utcnow()
            if publish:
                tpl.is_published = True
            session.add(tpl)

    data["blocks"] = blocks_in
    task.draft_json = data
    review = "published" if publish else "drafted"
    for t in batch_tasks:
        t.result_ref = {
            "plan_id": plan_id,
            "block_ids": created_block_ids,
            "published": bool(publish),
        }
        t.draft_json = data if t.id == task.id else t.draft_json
        t.review_state = review
        t.updated_at = utcnow()
        session.add(t)

    session.commit()
    return {"ok": True, "plan_id": plan_id, "block_ids": created_block_ids}
