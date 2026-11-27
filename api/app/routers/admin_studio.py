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
    cues: list[Any] | None = None
    mistakes: list[Any] | None = None
    instructions: list[Any] | None = None
    write_cues: bool = False


class DeriveFemaleIn(BaseModel):
    task_id: int
    source_exercise_id: str = Field(min_length=1, max_length=64)
    row_id: str | None = Field(default=None, max_length=64)
    copy_cues: bool = True


class RestoreCuesIn(BaseModel):
    task_id: int
    exercise_id: str = Field(min_length=1, max_length=64)


class PairCuesIn(BaseModel):
    task_id: int
    row_id: str = Field(min_length=1, max_length=64)
    exercise_id: str | None = None


class WriteCuesIn(BaseModel):
    task_id: int
    row_id: str = Field(min_length=1, max_length=64)
    cue_mode: str = Field(default="replace", max_length=16)
    pairs: list[dict[str, Any]] | None = None
    exercise_id: str | None = None  # 前端已绑但草稿未落盘时可由请求带上


class AttachDemoIn(BaseModel):
    task_id: int
    exercise_id: str = Field(min_length=1, max_length=64)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    # 优先写回这一行；缺省时按 exercise_id 扫草稿（兼容旧前端）
    row_id: str | None = Field(default=None, max_length=64)
    # False=只挂计划/草稿行（默认）；True=同时写入动作库 SKU 示范
    write_to_library: bool = False


class AttachHighlightIn(BaseModel):
    task_id: int
    exercise_id: str = Field(min_length=1, max_length=64)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    row_id: str | None = Field(default=None, max_length=64)
    # 教学视频默认写库（教练卡/详情页读 SKU）；False=只挂草稿行
    write_to_library: bool = True


class DraftIn(BaseModel):
    draft: dict[str, Any]


class ConfirmPlanIn(BaseModel):
    task_id: int
    draft: dict[str, Any] | None = None
    append_to_plan_id: str | None = None
    # 多条合成一套：额外勾选的其它可发布任务 id（不含 task_id）
    merge_task_ids: list[int] | None = None
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


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    """删除工坊任务（本地视频一并清掉；已发布计划不回滚）。"""
    return studio_service.delete_task(session, task_id)


@router.post("/tasks/{task_id}/skip-transcribe")
def skip_transcribe(
    task_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    """长视频转写卡住：跳过字幕进工作台，改手填。"""
    return studio_service.skip_transcribe(session, task_id)


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
        cues=body.cues,
        mistakes=body.mistakes,
        instructions=body.instructions,
        write_cues=body.write_cues,
    )


@router.post("/derive-female-variant")
def derive_female_variant(
    body: DeriveFemaleIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    """从男版/通用 SKU 派生女版并可选写回草稿行绑定。"""
    return studio_service.derive_female_variant_for_studio(
        session,
        task_id=body.task_id,
        source_exercise_id=body.source_exercise_id,
        row_id=body.row_id,
        copy_cues=body.copy_cues,
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
        row_id=body.row_id,
        write_to_library=body.write_to_library,
    )


@router.post("/attach-highlight")
def attach_highlight(
    body: AttachHighlightIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.attach_highlight_now(
        session,
        task_id=body.task_id,
        exercise_id=body.exercise_id,
        start=body.start,
        end=body.end,
        row_id=body.row_id,
        write_to_library=body.write_to_library,
    )


@router.post("/restore-cues")
def restore_cues(
    body: RestoreCuesIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    """后端保留；方案 A 前端不做还原入口。"""
    return studio_service.restore_sku_cues_from_backup(
        session, task_id=body.task_id, exercise_id=body.exercise_id
    )


@router.post("/pair-cues")
def pair_cues(
    body: PairCuesIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.pair_studio_cues(
        session,
        task_id=body.task_id,
        row_id=body.row_id,
        exercise_id=body.exercise_id,
    )


@router.post("/write-cues")
def write_cues(
    body: WriteCuesIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return studio_service.write_studio_cues(
        session,
        task_id=body.task_id,
        row_id=body.row_id,
        cue_mode=body.cue_mode,
        pairs=body.pairs,
        exercise_id=body.exercise_id,
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
        merge_task_ids=body.merge_task_ids,
        publish=body.publish,
    )
