"""内容工坊 Admin API：/api/admin/studio/*"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.auth import require_admin
from app.db import get_session
from app.services import studio_service

router = APIRouter(prefix="/api/admin/studio", tags=["admin-studio"])


class CookiesIn(BaseModel):
    source: str | None = "paste"  # paste | browser
    browser: str | None = "chrome"  # chrome|edge|firefox|brave|chromium
    bilibili: str | None = None
    douyin: str | None = None
    youtube: str | None = None


class PreviewClipIn(BaseModel):
    task_id: int
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class QuickCreateIn(BaseModel):
    task_id: int
    spoken_name: str = Field(min_length=1, max_length=120)
    muscle: str = Field(default="胸", max_length=16)
    gear: str = Field(default="器械", max_length=32)
    role: str = Field(default="isolation", max_length=16)
    start: float | None = None
    end: float | None = None
    attach_demo: bool = True


class AttachDemoIn(BaseModel):
    task_id: int
    exercise_id: str = Field(min_length=1, max_length=64)
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class DraftIn(BaseModel):
    draft: dict[str, Any]


class ConfirmPlanIn(BaseModel):
    task_id: int
    draft: dict[str, Any] | None = None
    append_to_plan_id: str | None = None
    publish: bool = True


class ReplaceSourceIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.put("/cookies")
def put_cookies(body: CookiesIn, _: object = Depends(require_admin)):
    return studio_service.save_cookies(body.model_dump())


@router.get("/cookies")
def get_cookies(_: object = Depends(require_admin)):
    data = studio_service.load_cookies()
    return {
        "source": data.get("source") or "paste",
        "browser": data.get("browser") or "chrome",
        "bilibili_set": bool(data.get("bilibili")),
        "douyin_set": bool(data.get("douyin")),
        "youtube_set": bool(data.get("youtube")),
        "updated_at": data.get("updated_at"),
        **data,
    }


@router.get("/deps")
def get_deps(_: object = Depends(require_admin)):
    return studio_service.studio_deps()


@router.post("/ingest-batch")
async def ingest_batch(
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    text: str | None = Form(default=None),
    mode: str = Form(default="plan_single"),
    merge_into_one_plan: bool = Form(default=False),
    plan_title: str | None = Form(default=None),
    pause_for_confirm: bool = Form(default=False),
    source_kind: str | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
):
    uploaded: list[tuple[str, bytes]] = []
    for f in files or []:
        raw = await f.read()
        uploaded.append((f.filename or "upload.mp4", raw))
    return studio_service.ingest_batch(
        session,
        text=text,
        mode=mode,
        merge_into_one_plan=merge_into_one_plan,
        plan_title=plan_title,
        files=uploaded,
        pause_for_confirm=pause_for_confirm,
        source_kind=source_kind,
    )


@router.get("/tasks")
def list_tasks(
    limit: int = 50,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.list_tasks(session, limit=limit)


@router.get("/tasks/{task_id}")
def get_task(
    task_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.get_task(session, task_id)


@router.post("/tasks/{task_id}/upload-fallback")
async def upload_fallback(
    task_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    file: UploadFile = File(...),
):
    return await studio_service.upload_fallback(session, task_id, file)


@router.post("/tasks/{task_id}/retry-download")
def retry_download(
    task_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.retry_download(session, task_id)


@router.post("/tasks/{task_id}/replace-source")
def replace_source(
    task_id: int,
    body: ReplaceSourceIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.replace_source(session, task_id, text=body.text)


@router.post("/tasks/{task_id}/continue")
def continue_pipeline(
    task_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.continue_pipeline(session, task_id)


@router.post("/tasks/{task_id}/retranscribe")
def retranscribe(
    task_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.retranscribe(session, task_id)


@router.post("/tasks/{task_id}/reparse")
def reparse(
    task_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.reparse(session, task_id)


@router.put("/tasks/{task_id}/draft")
def put_draft(
    task_id: int,
    body: DraftIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.update_task_draft(session, task_id, body.draft)


@router.post("/tasks/{task_id}/cover")
async def upload_task_cover(
    task_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    file: UploadFile = File(...),
):
    return await studio_service.upload_task_cover(session, task_id, file)


@router.post("/preview-clip")
def preview_clip(
    body: PreviewClipIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.preview_clip(
        session, task_id=body.task_id, start=body.start, end=body.end
    )


@router.post("/quick-create-exercise")
def quick_create(
    body: QuickCreateIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.quick_create_exercise(
        session,
        task_id=body.task_id,
        spoken_name=body.spoken_name,
        muscle=body.muscle,
        gear=body.gear,
        role=body.role,
        start=body.start,
        end=body.end,
        attach_demo=body.attach_demo,
    )


@router.post("/attach-demo")
def attach_demo(
    body: AttachDemoIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.attach_demo_now(
        session,
        task_id=body.task_id,
        exercise_id=body.exercise_id,
        start=body.start,
        end=body.end,
    )


@router.post("/confirm-plan")
def confirm_plan(
    body: ConfirmPlanIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.confirm_plan(
        session,
        task_id=body.task_id,
        draft=body.draft,
        append_to_plan_id=body.append_to_plan_id,
        publish=body.publish,
    )
