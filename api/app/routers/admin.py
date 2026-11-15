"""GymCoach Admin API — A0/A1 read + A2 write."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select

from app.auth import issue_admin_token, require_admin, verify_admin_password
from app.db import get_session
from app.models import Exercise, ExerciseAlias, ExerciseMedia
from app.services import admin_catalog, admin_editor, admin_media_pool

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AdminLoginIn(BaseModel):
    username: str = Field(default="admin", max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AdminLoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class ReviewFlagIn(BaseModel):
    needs_review: bool


class ExerciseUpdateIn(BaseModel):
    name_zh: str | None = None
    muscle: str | None = None
    sub_region: str | None = None
    movement_pattern: str | None = None
    gear: str | None = None
    modality: str | None = None
    coach_core: bool | None = None
    needs_review: bool | None = None
    joint_stress: dict[str, str] | None = None
    instructions_zh: list[str] | None = None
    cues_zh: list[str] | None = None
    common_mistakes_zh: list[str] | None = None
    aliases: list[str] | None = None


class ExerciseCreateIn(BaseModel):
    name_zh: str = Field(min_length=1, max_length=120)
    name_en: str | None = Field(default=None, max_length=160)
    id: str | None = Field(default=None, max_length=32)
    muscle: str | None = None
    sub_region: str | None = None
    movement_pattern: str | None = None
    gear: str | None = None
    modality: str | None = None
    coach_core: bool = False
    needs_review: bool = True
    aliases: list[str] | None = None
    instructions_zh: list[str] | None = None
    cues_zh: list[str] | None = None
    common_mistakes_zh: list[str] | None = None
    joint_stress: dict[str, str] | None = None


@router.get("/health")
def admin_health(session: Session = Depends(get_session)):
    exercise_total = session.exec(select(func.count()).select_from(Exercise)).one()
    coach_core = session.exec(
        select(func.count()).select_from(Exercise).where(Exercise.coach_core.is_(True))
    ).one()
    media_total = session.exec(select(func.count()).select_from(ExerciseMedia)).one()
    media_published = session.exec(
        select(func.count())
        .select_from(ExerciseMedia)
        .where(ExerciseMedia.status == "published")
    ).one()
    alias_total = session.exec(select(func.count()).select_from(ExerciseAlias)).one()
    with_start = session.exec(
        select(func.count())
        .select_from(Exercise)
        .where(col(Exercise.image_start).is_not(None), Exercise.image_start != "")
    ).one()
    return {
        "ok": True,
        "service": "gym-admin",
        "exercises": int(exercise_total or 0),
        "coach_core": int(coach_core or 0),
        "media": int(media_total or 0),
        "media_published": int(media_published or 0),
        "aliases": int(alias_total or 0),
        "with_image_start": int(with_start or 0),
    }


@router.post("/auth/login", response_model=AdminLoginOut)
def admin_login(body: AdminLoginIn):
    if not verify_admin_password(body.password):
        raise HTTPException(status_code=401, detail="账号或密码不对")
    username = (body.username or "admin").strip() or "admin"
    return AdminLoginOut(access_token=issue_admin_token(username), username=username)


@router.get("/auth/me")
def admin_me(_: object = Depends(require_admin)):
    return {"ok": True, "role": "admin"}


@router.get("/stats/overview")
def stats_overview(
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_catalog.build_overview(session)


@router.get("/exercises")
def list_exercises(
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    q: str | None = Query(default=None),
    muscle: str | None = Query(default=None),
    sub_region: str | None = Query(default=None),
    gear: str | None = Query(default=None),
    movement_pattern: str | None = Query(default=None),
    coach_core: bool | None = Query(default=None),
    media_state: str | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    return admin_catalog.list_exercises(
        session,
        q=q,
        muscle=muscle,
        sub_region=sub_region,
        gear=gear,
        movement_pattern=movement_pattern,
        coach_core=coach_core,
        media_state=media_state,
        needs_review=needs_review,
        page=page,
        page_size=page_size,
    )


@router.post("/exercises")
def post_exercise(
    body: ExerciseCreateIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_editor.create_exercise(session, body.model_dump())


@router.get("/exercises/{exercise_id}")
def get_exercise(
    exercise_id: str,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    detail = admin_editor.get_editable_detail(session, exercise_id)
    if not detail:
        raise HTTPException(status_code=404, detail="动作不存在")
    return detail


@router.put("/exercises/{exercise_id}")
def put_exercise(
    exercise_id: str,
    body: ExerciseUpdateIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_editor.update_exercise(
        session,
        exercise_id,
        body.model_dump(exclude_unset=True),
    )


@router.patch("/exercises/{exercise_id}/review-flag")
def patch_review_flag(
    exercise_id: str,
    body: ReviewFlagIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    result = admin_catalog.set_review_flag(session, exercise_id, body.needs_review)
    if not result:
        raise HTTPException(status_code=404, detail="动作不存在")
    return result


@router.post("/exercises/{exercise_id}/media")
async def post_exercise_media(
    exercise_id: str,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    role: str = Form(...),
    publish: bool = Form(False),
    file: UploadFile = File(...),
):
    return await admin_editor.upload_media(
        session,
        exercise_id,
        role=role,
        file=file,
        publish=publish,
    )


@router.post("/exercises/{exercise_id}/ai-draft")
async def post_ai_draft(
    exercise_id: str,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return await admin_editor.ai_draft(session, exercise_id)


@router.post("/media/{media_id}/publish")
def post_publish_media(
    media_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_editor.publish_media(session, media_id)


@router.post("/media/{media_id}/rollback")
def post_rollback_media(
    media_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_editor.rollback_media(session, media_id)


@router.delete("/exercises/{exercise_id}/media/{role}")
def delete_exercise_slot(
    exercise_id: str,
    role: str,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_editor.clear_slot(session, exercise_id, role)


class PoolBindIn(BaseModel):
    exercise_id: str = Field(min_length=1, max_length=32)
    role: str | None = None
    publish: bool = False


@router.post("/media/batch")
async def post_media_batch(
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    files: list[UploadFile] = File(...),
    relative_paths: list[str] | None = Form(default=None),
    publish: bool = Form(False),
):
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个文件")
    return await admin_media_pool.batch_upload(
        session,
        files,
        relative_paths,
        publish=publish,
    )


@router.get("/media-pool")
def get_media_pool(
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    status: str | None = Query(default="pending"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    return admin_media_pool.list_pool(
        session,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/media-pool/search")
def search_media_pool_bind(
    q: str = Query(default=""),
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    limit: int = Query(default=12, ge=1, le=30),
):
    return {"items": admin_media_pool.search_exercises_for_bind(session, q, limit=limit)}


@router.post("/media-pool/{pool_id}/bind")
def post_media_pool_bind(
    pool_id: int,
    body: PoolBindIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_media_pool.bind_pool_item(
        session,
        pool_id,
        exercise_id=body.exercise_id,
        role=body.role,
        publish=body.publish,
    )


@router.post("/media-pool/{pool_id}/ignore")
def post_media_pool_ignore(
    pool_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_media_pool.ignore_pool_item(session, pool_id)
