"""内容工坊：批量贴口令 → 下载/字幕/拆计划 → 审核发布。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
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


def _task_out(task: StudioTask) -> dict[str, Any]:
    play_url = None
    if task.stored_path:
        p = task.stored_path.replace("\\", "/")
        play_url = p if p.startswith(("http://", "https://", "/static/")) else f"/static/{p}"
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
        "transcript_json": task.transcript_json or {},
        "draft_json": task.draft_json or {},
        "score": task.score or {},
        "review_state": task.review_state,
        "result_ref": task.result_ref or {},
        "error": task.error,
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

    for url in urls:
        task = StudioTask(
            batch_id=batch_id,
            batch_order=order,
            source_type="link",
            source_text=(text or "")[:2000] if order == 0 else url,
            source_url=url,
            mode=mode,
            status="queued",
            progress=0,
            draft_json={"plan_title": title} if title else {},
            review_state="needs_review",
        )
        session.add(task)
        session.flush()
        created.append(task)
        order += 1

    for filename, raw in uploads:
        if not raw:
            continue
        task = StudioTask(
            batch_id=batch_id,
            batch_order=order,
            source_type="upload",
            source_text=filename,
            source_url=None,
            mode=mode,
            status="queued",
            progress=5,
            draft_json={"plan_title": title} if title else {},
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
    if task.status not in _RELINK_STATUSES:
        raise HTTPException(status_code=400, detail=f"当前状态「{task.status}」不可重试下载")
    _reset_task_media(task_id)
    _touch(
        task,
        stored_path=None,
        source_type="link",
        status="queued",
        progress=0,
        error=None,
        transcript_json=None,
    )
    session.add(task)
    session.commit()
    _spawn_pipeline(task_id)
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
                _touch(task, status="failed", error=str(e)[:500], progress=100)
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
        session.add(task)
        session.commit()
        ok, err = _download_url(task)
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

    # 2) transcribe
    _touch(task, status="transcribing", progress=40)
    session.add(task)
    session.commit()
    transcript = _transcribe(video)
    task.transcript_json = transcript
    task.progress = 65

    # 3) parse + score
    _touch(task, status="parsing", progress=75)
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


def _friendly_download_error(raw: str) -> str:
    text = (raw or "").strip()
    low = text.lower()
    if "fresh cookies" in low or "http error 403" in low or "403: forbidden" in low:
        return (
            "抖音拒绝访问（403/需要新鲜 Cookie）。请任选其一："
            "① 平台 Cookie 选「从本机浏览器读取」并先在该浏览器打开并登录 www.douyin.com；"
            "② 用扩展 Get cookies.txt LOCALLY 导出 Netscape 文本贴进抖音框；"
            "③ 补传本地 MP4。"
        )
    if "could not copy" in low and "cookie database" in low:
        return (
            "无法读取浏览器 Cookie 库（浏览器可能正占用数据库）。"
            "请先完全退出 Chrome/Edge 再点「重新下载」，或改用扩展导出 cookies.txt 粘贴。"
        )
    return text[-800:] if text else "下载失败"


def _download_url(task: StudioTask) -> tuple[bool, str | None]:
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
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "下载超时（120s）；请检查 Cookie 是否有效，或补传本地 MP4"
    # 找产出
    files = sorted(_task_dir(task.id).glob("source.*"))
    mp4s = [f for f in files if f.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov")]
    if proc.returncode != 0 or not mp4s:
        return False, _friendly_download_error(proc.stderr or proc.stdout or "下载失败")
    dest = mp4s[0]
    task.stored_path = f"/static/studio/{task.id}/{dest.name}"
    return True, None


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

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments_out: list[dict[str, Any]] = []
    texts: list[str] = []
    segs, _info = model.transcribe(str(video), language="zh", vad_filter=True)
    for s in segs:
        row = {"start": round(float(s.start), 2), "end": round(float(s.end), 2), "text": (s.text or "").strip()}
        if row["text"]:
            segments_out.append(row)
            texts.append(row["text"])
    return {"engine": "faster-whisper", "segments": segments_out, "text": "\n".join(texts)}


def _muscle_from_hit(hit: dict[str, Any] | None) -> str:
    """只用动作库字段；无命中则占位「全身」，由人工改。"""
    if not hit:
        return "全身"
    m = str(hit.get("muscle") or "").strip()
    return m if m in _KNOWN_MUSCLES else "全身"


def _parse_and_score(
    session: Session, task: StudioTask, transcript: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    text = str(transcript.get("text") or "")
    segments = list(transcript.get("segments") or [])
    ensure_loaded()

    # 从字幕里捞动作名（目录子串命中）
    mentions = find_catalog_mentions_in_text(text) if text else []
    exercises: list[dict[str, Any]] = []

    if mentions:
        for i, name in enumerate(mentions[:12]):
            snip = _snippet_for_name(segments, name)
            hit = _match_exercise(session, name)
            conf = float(hit["confidence"]) if hit else 0.0
            exercises.append(
                {
                    "id": f"row-{i}",
                    "spoken_name": name,
                    "exercise_id": hit["id"] if hit else None,
                    "exercise_name": hit["name_zh"] if hit else name,
                    "target_muscle": _muscle_from_hit(hit),
                    "role": "main" if i < 2 else ("assist" if i < 4 else "isolation"),
                    "target_sets": None,
                    "target_reps": None,
                    "sets_from_transcript": False,
                    "source_kind": "spoken",
                    "match_confidence": conf,
                    "snippet": snip,
                    "traffic": "red",
                    "replace_demo": False,
                    "attach_demo": not bool(hit and hit.get("has_demo")),
                }
            )
    elif text:
        # 无目录命中：按「第N个动作」粗切
        parts = re.split(r"(?:第[一二三四五六七八九十\d]+个动作|下一个动作|正式组)", text)
        for i, part in enumerate(parts[1:7], start=0):
            spoken = (part.strip()[:40] or f"未识别动作{i+1}")
            snip = _snippet_for_name(segments, spoken[:6]) if segments else {"start": 10.0 * i, "end": 10.0 * i + 5}
            exercises.append(
                {
                    "id": f"row-{i}",
                    "spoken_name": spoken,
                    "exercise_id": None,
                    "exercise_name": None,
                    "target_muscle": "全身",
                    "role": "main" if i == 0 else "assist",
                    "target_sets": None,
                    "target_reps": None,
                    "sets_from_transcript": False,
                    "source_kind": "spoken",
                    "match_confidence": 0.1,
                    "snippet": snip,
                    "traffic": "red",
                    "replace_demo": False,
                    "attach_demo": True,
                }
            )

    # 从文本补组次（整段字幕扫一次；命中则记 sets_from_transcript）
    sets_match = _SETS_RE.search(text) if text else None
    for ex in exercises:
        if sets_match and ex.get("target_sets") is None:
            ex["target_sets"] = int(sets_match.group("sets"))
            if sets_match.group("reps_a") and sets_match.group("reps_b"):
                ex["target_reps"] = f"{sets_match.group('reps_a')}-{sets_match.group('reps_b')}"
            elif sets_match.group("reps"):
                ex["target_reps"] = str(sets_match.group("reps"))
            ex["sets_from_transcript"] = True

    # 未解析到组次：保留默认建议，但不得假绿灯
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
            ex["traffic"] = "amber"  # 库已绑上，组次是默认建议，需瞄一眼
        else:
            ex["traffic"] = "red"

    if not exercises:
        exercises = [
            {
                "id": "row-0",
                "spoken_name": "待人工补充",
                "exercise_id": None,
                "exercise_name": None,
                "target_muscle": "全身",
                "role": "main",
                "target_sets": 3,
                "target_reps": "8-12",
                "sets_from_transcript": False,
                "source_kind": "missing",
                "match_confidence": 0.0,
                "snippet": {"start": 0, "end": 5},
                "traffic": "red",
                "replace_demo": False,
                "attach_demo": True,
            }
        ]

    muscle = exercises[0].get("target_muscle") or "全身"
    title = (task.draft_json or {}).get("plan_title") if isinstance(task.draft_json, dict) else None
    if not title:
        title = f"工坊草稿 · {muscle}" if task.mode != "exercise_only" else "动作素材草稿"

    block_title = {
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
        "blocks": [
            {
                "title": block_title,
                "muscles": [muscle] if muscle != "全身" else [],
                "exercises": exercises,
            }
        ],
    }
    red = sum(1 for e in exercises if e.get("traffic") == "red")
    amber = sum(1 for e in exercises if e.get("traffic") == "amber")
    green = sum(1 for e in exercises if e.get("traffic") == "green")
    score = {
        "red_count": red,
        "amber_count": amber,
        "green_count": green,
        "total": len(exercises),
    }
    return draft, score


def _snippet_for_name(segments: list[dict[str, Any]], name: str) -> dict[str, float]:
    key = (name or "")[:4]
    for seg in segments:
        if key and key in str(seg.get("text") or ""):
            start = float(seg.get("start") or 0)
            end = float(seg.get("end") or (start + 5))
            # 扩成 3~6 秒示范窗
            mid = (start + end) / 2
            return {"start": round(max(0, mid - 2.5), 2), "end": round(mid + 2.5, 2)}
    if segments:
        s0 = float(segments[0].get("start") or 0)
        return {"start": s0, "end": s0 + 5}
    return {"start": 0.0, "end": 5.0}


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
    return {"id": ex.id, "name_zh": ex.name_zh, "muscle": ex.muscle, "confidence": conf, "has_demo": has_demo}


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

    ex = session.get(Exercise, exercise_id)
    if ex and not ex.image_start:
        ex.image_start = cover_url
        session.add(ex)
        # 同时挂 start 槽
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
    session.commit()
    return {"demo_url": demo_url, "cover_url": cover_url}


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
