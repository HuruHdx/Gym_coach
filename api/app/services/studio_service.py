"""内容工坊：批量贴口令 → 下载/字幕/拆计划 → 审核发布。"""

from __future__ import annotations

import json
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


def _task_out(task: StudioTask) -> dict[str, Any]:
    play_url = None
    if task.stored_path:
        p = task.stored_path.replace("\\", "/")
        play_url = p if p.startswith(("http://", "https://", "/static/")) else f"/static/{p}"
    draft = task.draft_json or {}
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
    return {"items": [_task_out(t) for t in rows], "total": len(rows)}


def get_task(session: Session, task_id: int) -> dict[str, Any]:
    task = session.get(StudioTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_out(task)


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
    synced = _sync_sku_text_from_draft(session, task, exercise_id)
    session.commit()
    return {"ok": True, "exercise_id": exercise_id, "demo": meta, "synced_text": synced}


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


def _spawn_pipeline(task_id: int) -> None:
    t = threading.Thread(target=_run_pipeline_safe, args=(task_id,), daemon=True)
    t.start()


def _run_pipeline_safe(task_id: int) -> None:
    from app.db import engine

    try:
        with Session(engine) as session:
            _run_pipeline(session, task_id)
    except Exception as e:  # noqa: BLE001
        with Session(engine) as session:
            task = session.get(StudioTask, task_id)
            if task:
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


def _run_pipeline(session: Session, task_id: int) -> None:
    task = session.get(StudioTask, task_id)
    if not task:
        return

    # 1) download
    if not task.stored_path and task.source_url:
        _touch(task, status="downloading", progress=10, error=None)
        _set_live(task, stage="downloading", percent=0)
        session.add(task)
        session.commit()

        def _on_download(meta: dict[str, Any]) -> None:
            fresh = session.get(StudioTask, task_id)
            if not fresh:
                return
            pct = int(meta.get("percent") or 0)
            fresh.progress = min(38, 10 + int(pct * 0.28))
            _set_live(fresh, **meta)
            session.add(fresh)
            session.commit()

        ok, err = _download_url(task, on_progress=_on_download)
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

    # 2) transcribe
    _touch(task, status="transcribing", progress=40)
    _set_live(task, stage="transcribing", percent=40)
    session.add(task)
    session.commit()
    transcript = _transcribe(video)
    task.transcript_json = transcript
    task.progress = 65

    # 3) parse + score
    _touch(task, status="parsing", progress=75)
    _set_live(task, stage="parsing", percent=75)
    session.add(task)
    session.commit()
    draft, score = _parse_and_score(session, task, transcript)
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


def _friendly_download_error(raw: str) -> str:
    text = (raw or "").strip()
    low = text.lower()
    if "fresh cookies" in low or "http error 403" in low or "403: forbidden" in low:
        return (
            "平台拒绝访问（需要新鲜 Cookie）。"
            "请用「从本机浏览器读取」或导出 cookies.txt，也可补传本地 MP4。"
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


def _download_url(
    task: StudioTask,
    *,
    on_progress: Any = None,
) -> tuple[bool, str | None]:
    assert task.id and task.source_url
    out_tmpl = str(_task_dir(task.id) / "source.%(ext)s")
    cookies = load_cookies()
    cookie_arg: list[str] = []
    source = str(cookies.get("source") or "paste")
    if source == "browser":
        browser = str(cookies.get("browser") or "chrome")
        cookie_arg = ["--cookies-from-browser", browser]
    else:
        blob = _pick_cookie_blob(cookies, task.source_url)
        if blob.strip():
            jar = _task_dir(task.id) / "cookies.txt"
            jar.write_text(
                _to_netscape_cookie_file(blob, _cookie_domains_for_url(task.source_url)),
                encoding="utf-8",
            )
            cookie_arg = ["--cookies", str(jar)]

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
        "--referer",
        "https://www.douyin.com/",
        "-f",
        "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format",
        "mp4",
        "-o",
        out_tmpl,
        *cookie_arg,
        task.source_url,
    ]
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
    if stalled:
        return False, "下载超过 30 秒没有新进度，已中断。可重新下载，或补传本地 MP4。"
    files = sorted(_task_dir(task.id).glob("source.*"))
    mp4s = [f for f in files if f.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov")]
    if proc.returncode not in (0, None) or not mp4s:
        return False, _friendly_download_error("\n".join(log_lines) or "下载失败")
    dest = mp4s[0]
    task.stored_path = f"/static/studio/{task.id}/{dest.name}"
    return True, None


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


def _transcribe(video: Path) -> dict[str, Any]:
    """优先 Faster-Whisper；没有则返回空字幕骨架，仍可人工审/启发式。"""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return {
            "engine": "none",
            "warning": "未安装 faster-whisper，已跳过自动字幕；可手动审或稍后安装",
            "segments": [],
            "text": "",
        }

    _patch_av_open_compat()
    # 先用 ffmpeg 抽 16k mono wav，绕开部分损坏容器；失败则直接喂原视频
    wav = video.with_suffix(".whisper16k.wav")
    audio_path = video
    try:
        from app.services.media_clip import resolve_ffmpeg

        ff = resolve_ffmpeg()
        if ff:
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
                timeout=600,
            )
            if wav.exists() and wav.stat().st_size > 44:
                audio_path = wav
    except Exception:
        audio_path = video

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments_out: list[dict[str, Any]] = []
    texts: list[str] = []
    try:
        segs, _info = model.transcribe(str(audio_path), language="zh", vad_filter=True)
        for s in segs:
            row = {
                "start": round(float(s.start), 2),
                "end": round(float(s.end), 2),
                "text": (s.text or "").strip(),
            }
            if row["text"]:
                segments_out.append(row)
                texts.append(row["text"])
    finally:
        if wav.exists():
            try:
                wav.unlink()
            except OSError:
                pass
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


_STUDIO_PARSE_SYSTEM = """你是健身房跟练视频拆课助手。根据带时间戳的口播字幕，抽出正式训练动作清单。
规则：
1. 只抽正式组抗阻动作；跳过开场、闲聊、纯热身口头叮嘱、收尾拉伸（除非明确是正式动作）。
2. spoken_name 用教练口中的标准动作名（如「高位下拉」「杠铃划船」），不要「上背部拉伸」这类含糊说法；看不清就写口语原词。
3. target_muscle 只能是：胸/背/肩/腿/臂/核心。
4. role：main / assist / isolation / warmup。
5. spoken_at 是「讲到这个动作名」的秒数（字幕时间），不是示范画面起点。
6. cues / mistakes 各 0～3 条，必须来自字幕里的要领/易错，并带 source_at（对应字幕秒数）；没有就空数组，禁止编造。
7. tempo / intensity 有则摘一句，无则空字符串。
8. 组次未提及时 target_sets/target_reps 置 null。
只输出 JSON：
{
  "plan_title": "短标题",
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
}"""


def _llm_extract_plan(transcript: dict[str, Any], task: StudioTask) -> dict[str, Any] | None:
    """DeepSeek（openai_compatible）拆课；失败或 mock 返回 None，由启发式兜底。"""
    from app.brain.llm import MockLLM, TEMPERATURE_STRUCTURED, get_llm

    llm = get_llm()
    if isinstance(llm, MockLLM):
        return None
    segments = list(transcript.get("segments") or [])
    if not segments and not transcript.get("text"):
        return None
    lines: list[str] = []
    for seg in segments[:220]:
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{_fmt_mmss(float(seg.get('start') or 0))}] {text}")
    body = "\n".join(lines) if lines else str(transcript.get("text") or "")[:12000]
    if len(body) > 14000:
        body = body[:14000] + "\n…(字幕过长已截断)"
    hint = ""
    if isinstance(task.draft_json, dict) and task.draft_json.get("plan_title"):
        hint = f"已知计划名倾向：{task.draft_json.get('plan_title')}\n"
    user = (
        f"{hint}视频模式：{task.mode}\n"
        f"下面是 whisper 口播字幕（[mm:ss] 原文）。请拆出正式动作：\n\n{body}"
    )
    try:
        raw = _run_coro(
            llm.complete_json(_STUDIO_PARSE_SYSTEM, user, temperature=TEMPERATURE_STRUCTURED)
        )
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    exs = raw.get("exercises")
    if not isinstance(exs, list) or not exs:
        return None
    return raw


def _finalize_exercise_traffic(exercises: list[dict[str, Any]]) -> None:
    for ex in exercises:
        if ex.get("target_sets") is None:
            ex["target_sets"] = 3
            ex["target_reps"] = ex.get("target_reps") or "8-12"
            ex["sets_from_transcript"] = False
        conf = float(ex.get("match_confidence") or 0)
        matched = bool(ex.get("exercise_id")) and conf >= 0.75
        if matched and ex.get("sets_from_transcript"):
            ex["traffic"] = "green"
        elif matched:
            ex["traffic"] = "amber"
        else:
            ex["traffic"] = "red"


def _build_draft(
    task: StudioTask,
    exercises: list[dict[str, Any]],
    *,
    title: str | None,
    block_title: str | None,
    muscle: str | None,
    parse_engine: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _finalize_exercise_traffic(exercises)
    muscle = muscle if muscle in _KNOWN_MUSCLES else (
        (exercises[0].get("target_muscle") if exercises else None) or "全身"
    )
    if muscle not in _KNOWN_MUSCLES:
        muscle = "全身"
    kept_title = None
    if isinstance(task.draft_json, dict):
        kept_title = task.draft_json.get("plan_title")
    title = title or kept_title
    if not title:
        title = f"工坊草稿 · {muscle}" if task.mode != "exercise_only" else "动作素材草稿"
    block_title = block_title or {
        "胸": "推日 / 胸",
        "背": "拉日 / 背",
        "肩": "肩部",
        "腿": "腿日",
        "臂": "手臂",
        "核心": "核心",
        "全身": "待定部位",
    }.get(str(muscle), str(muscle))
    draft = {
        "plan_title": title,
        "scene_tag": "博主同款" if task.mode != "exercise_only" else None,
        "mode": task.mode,
        "parse_engine": parse_engine,
        "blocks": [
            {
                "title": block_title,
                "muscles": [muscle] if muscle != "全身" else [],
                "exercises": exercises,
            }
        ],
    }
    score = {
        "red_count": sum(1 for e in exercises if e.get("traffic") == "red"),
        "amber_count": sum(1 for e in exercises if e.get("traffic") == "amber"),
        "green_count": sum(1 for e in exercises if e.get("traffic") == "green"),
        "total": len(exercises),
        "parse_engine": parse_engine,
    }
    return draft, score


def _parse_and_score(
    session: Session, task: StudioTask, transcript: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    text = str(transcript.get("text") or "")
    segments = list(transcript.get("segments") or [])
    ensure_loaded()

    # 1) DeepSeek / 兼容 LLM
    llm_raw = _llm_extract_plan(transcript, task)
    if llm_raw:
        exercises: list[dict[str, Any]] = []
        for i, item in enumerate(llm_raw.get("exercises") or []):
            if not isinstance(item, dict):
                continue
            spoken = str(item.get("spoken_name") or "").strip()
            if not spoken:
                continue
            spoken_at = float(item.get("spoken_at") or 0)
            snip = {
                "start": round(max(0.0, spoken_at - 1.0), 2),
                "end": round(spoken_at + 5.0, 2),
                "spoken_at": round(spoken_at, 2),
            }
            # 若字幕里能对准动作名，用更准的 spoken_at
            aligned = _snippet_for_name(segments, spoken) if segments else None
            if aligned and abs(float(aligned.get("spoken_at") or 0) - spoken_at) < 45:
                snip = aligned
            hit = _match_exercise(session, spoken)
            role = str(item.get("role") or "main")
            if role not in ("main", "assist", "isolation", "warmup"):
                role = "main"
            row = _exercise_draft_row(
                i=i,
                spoken=spoken,
                hit=hit,
                snip=snip,
                segments=segments,
                role=role,
                attach_demo=not bool(hit and hit.get("has_demo")),
                source_kind="spoken",
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
            exercises.append(row)
        if exercises:
            return _build_draft(
                task,
                exercises,
                title=str(llm_raw.get("plan_title") or "").strip() or None,
                block_title=str(llm_raw.get("block_title") or "").strip() or None,
                muscle=str(llm_raw.get("target_muscle") or "").strip() or None,
                parse_engine="llm",
            )

    # 2) 启发式兜底（目录子串 / 第N个动作）
    exercises = []
    mentions = find_catalog_mentions_in_text(text) if text else []
    if mentions:
        for i, name in enumerate(mentions[:12]):
            snip = _snippet_for_name(segments, name)
            hit = _match_exercise(session, name)
            exercises.append(
                _exercise_draft_row(
                    i=i,
                    spoken=name,
                    hit=hit,
                    snip=snip,
                    segments=segments,
                    role="main" if i < 2 else ("assist" if i < 4 else "isolation"),
                    attach_demo=not bool(hit and hit.get("has_demo")),
                )
            )
    elif text:
        parts = re.split(r"(?:第[一二三四五六七八九十\d]+个动作|下一个动作|正式组)", text)
        for i, part in enumerate(parts[1:7], start=0):
            spoken = (part.strip()[:40] or f"未识别动作{i+1}")
            snip = (
                _snippet_for_name(segments, spoken[:6])
                if segments
                else {"start": 10.0 * i, "end": 10.0 * i + 5, "spoken_at": 10.0 * i}
            )
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
        exercises,
        title=None,
        block_title=None,
        muscle=None,
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
) -> dict[str, Any]:
    confidence = float(conf if conf is not None else (hit["confidence"] if hit else 0.0))
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
        "match_confidence": confidence,
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
    }


def _snippet_for_name(segments: list[dict[str, Any]], name: str) -> dict[str, float]:
    key = (name or "")[:4]
    for seg in segments:
        if key and key in str(seg.get("text") or ""):
            start = float(seg.get("start") or 0)
            end = float(seg.get("end") or (start + 5))
            # spoken_at ≈ 他讲到这句的秒；选区给人拖，不直接当切片起点
            mid = (start + end) / 2
            return {
                "start": round(max(0, mid - 2.5), 2),
                "end": round(mid + 2.5, 2),
                "spoken_at": round(start, 2),
            }
    if segments:
        s0 = float(segments[0].get("start") or 0)
        return {"start": s0, "end": s0 + 5, "spoken_at": s0}
    return {"start": 0.0, "end": 5.0, "spoken_at": 0.0}


def _match_exercise(session: Session, spoken: str) -> dict[str, Any] | None:
    name = canonicalize_exercise(spoken)
    ex = session.exec(select(Exercise).where(Exercise.name_zh == name)).first()
    if not ex:
        # 别名
        alias = session.exec(select(ExerciseAlias).where(ExerciseAlias.alias == name)).first()
        if alias:
            ex = session.get(Exercise, alias.exercise_id)
    if not ex:
        # 模糊：包含
        rows = session.exec(
            select(Exercise).where(col(Exercise.name_zh).contains(spoken[:4])).limit(5)  # type: ignore[arg-type]
        ).all()
        ex = rows[0] if rows else None
    if not ex:
        return None
    has_demo = bool(
        session.exec(
            select(ExerciseMedia).where(
                ExerciseMedia.exercise_id == ex.id,
                ExerciseMedia.role == "demo",
                ExerciseMedia.status == "published",
            )
        ).first()
    )
    conf = 0.95 if ex.name_zh == name else 0.8
    return {
        "id": ex.id,
        "name_zh": ex.name_zh,
        "muscle": ex.muscle,
        "gear": ex.gear,
        "confidence": conf,
        "has_demo": has_demo,
    }


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
) -> dict[str, Any]:
    from app.services import admin_editor

    name = (spoken_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="动作名不能为空")
    created = admin_editor.create_exercise(
        session,
        {
            "name_zh": name,
            "muscle": muscle or "全身",
            "gear": gear or "器械",
            "modality": "抗阻",
            "aliases": [name],
            "coach_core": False,
            "needs_review": False,
        },
    )
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
    # 把工坊 LLM 要点同步进 SKU（H5「动作要领 / 发力提示」）
    _sync_sku_text_from_draft(session, task, exercise_id)
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


def _sync_sku_text_from_draft(
    session: Session, task: StudioTask, exercise_id: str
) -> dict[str, Any]:
    """工坊草稿里的 cues/mistakes → Exercise.cues_zh / common_mistakes_zh / instructions_zh。

    以前只把示范媒体写进 SKU，LLM 要点留在草稿，SKU/H5 一直「暂无教案」。
    """
    row = _draft_row_for_exercise(task, exercise_id)
    ex = session.get(Exercise, exercise_id)
    if not row or not ex:
        return {"ok": False, "reason": "no_draft_row"}

    cues = _line_texts(row.get("cues"))
    mistakes = _line_texts(row.get("mistakes"))
    changed = False
    if cues:
        ex.cues_zh = cues
        # H5「动作要领」读 instructions；工坊 LLM 通常只给 cues → 空教案时用 cues 填
        if not (ex.instructions_zh or []):
            ex.instructions_zh = cues[:4]
        changed = True
    if mistakes:
        ex.common_mistakes_zh = mistakes
        changed = True
    if changed:
        ex.updated_at = utcnow()
        session.add(ex)
    return {
        "ok": changed,
        "cues": cues,
        "mistakes": mistakes,
        "instructions": list(ex.instructions_zh or [])[:4],
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
        task.result_ref = {"mode": "exercise_only", "attached": attached}
        task.updated_at = utcnow()
        session.add(task)
        session.commit()
        return {"ok": True, "plan_id": None, "block_ids": [], "attached": attached}

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

    for t in batch_tasks:
        t.result_ref = {"plan_id": plan_id, "block_ids": created_block_ids}
        t.updated_at = utcnow()
        session.add(t)

    session.commit()
    return {"ok": True, "plan_id": plan_id, "block_ids": created_block_ids}
