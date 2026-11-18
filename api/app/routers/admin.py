"""GymCoach Admin API — A0/A1 read + A2 write."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select

from app.auth import issue_admin_token, require_admin, verify_admin_password
from app.db import get_session
from app.models import Exercise, ExerciseAlias, ExerciseMedia
from app.services import admin_catalog, admin_editor, admin_media_pool, admin_plans

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
    slot_roles: list[str] | None = None


class PlanCreateIn(BaseModel):
    id: str | None = Field(default=None, max_length=32)
    title: str = Field(min_length=1, max_length=80)
    subtitle: str | None = None
    author: str | None = None
    badge_label: str | None = None
    template_type: str = "framework"
    level: str | None = None
    days_per_week: int = Field(default=3, ge=1, le=7)
    minutes_min: int | None = Field(default=None, ge=1, le=300)
    minutes_max: int | None = Field(default=None, ge=1, le=300)
    muscle_tags: list[str] | None = None
    split_summary: str | None = None
    gear_tags: list[str] | None = None
    description: str | None = None
    cover_url: str | None = None
    scene_tag: str | None = None
    is_published: bool = False
    sort_order: int = 0


class PlanUpdateIn(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    badge_label: str | None = None
    template_type: str | None = None
    level: str | None = None
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    minutes_min: int | None = Field(default=None, ge=1, le=300)
    minutes_max: int | None = Field(default=None, ge=1, le=300)
    muscle_tags: list[str] | None = None
    split_summary: str | None = None
    gear_tags: list[str] | None = None
    description: str | None = None
    cover_url: str | None = None
    scene_tag: str | None = None
    is_published: bool | None = None
    sort_order: int | None = None


class PlanBlockIn(BaseModel):
    title: str | None = None
    muscles: list[str] | None = None
    minutes_min: int | None = Field(default=None, ge=1, le=300)
    minutes_max: int | None = Field(default=None, ge=1, le=300)
    cover_url: str | None = None
    note: str | None = None
    order_index: int | None = None


class PlanExerciseIn(BaseModel):
    exercise_id: str | None = None
    exercise_name: str | None = None
    role: str | None = None
    lock_level: str | None = None
    target_muscle: str | None = None
    target_sets: int | None = Field(default=None, ge=1, le=20)
    target_reps: str | None = None
    warmup_sets: int | None = Field(default=None, ge=0, le=10)
    alternatives: list[str] | None = None
    note: str | None = None
    order_index: int | None = None


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
    sort: str | None = Query(default="updated_desc"),
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
        sort=sort,
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


# ---------- 计划模板 ----------


@router.get("/plans")
def list_plans(
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    q: str | None = Query(default=None),
    type: str | None = Query(default=None, description="framework | fixed"),
    published: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
):
    return admin_plans.list_admin_plans(
        session,
        q=q,
        template_type=type,
        published=published,
        page=page,
        page_size=page_size,
    )


@router.post("/plans")
def post_plan(
    body: PlanCreateIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_plans.create_admin_plan(session, body.model_dump())


@router.get("/plans/{plan_id}")
def get_plan(
    plan_id: str,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_plans.get_admin_plan(session, plan_id)


@router.put("/plans/{plan_id}")
def put_plan(
    plan_id: str,
    body: PlanUpdateIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_plans.update_admin_plan(session, plan_id, body.model_dump(exclude_unset=True))


@router.delete("/plans/{plan_id}")
def delete_plan(
    plan_id: str,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_plans.delete_admin_plan(session, plan_id)


@router.post("/plans/{plan_id}/cover")
async def post_plan_cover(
    plan_id: str,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    file: UploadFile = File(...),
):
    return await admin_plans.upload_plan_cover(session, plan_id, file)


@router.post("/plans/{plan_id}/blocks")
def post_plan_block(
    plan_id: str,
    body: PlanBlockIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    data = body.model_dump(exclude_unset=True)
    if not data.get("title"):
        raise HTTPException(status_code=400, detail="板块标题不能为空")
    return admin_plans.create_block(session, plan_id, data)


@router.put("/plan-blocks/{block_id}")
def put_plan_block(
    block_id: int,
    body: PlanBlockIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_plans.update_block(session, block_id, body.model_dump(exclude_unset=True))


@router.post("/plan-blocks/{block_id}/cover")
async def post_plan_block_cover(
    block_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
    file: UploadFile = File(...),
):
    return await admin_plans.upload_block_cover(session, block_id, file)


@router.delete("/plan-blocks/{block_id}")
def delete_plan_block(
    block_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_plans.delete_block(session, block_id)


@router.post("/plan-blocks/{block_id}/exercises")
def post_plan_exercise(
    block_id: int,
    body: PlanExerciseIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_plans.create_plan_exercise(session, block_id, body.model_dump(exclude_unset=True))


@router.put("/plan-exercises/{ex_id}")
def put_plan_exercise(
    ex_id: int,
    body: PlanExerciseIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_plans.update_plan_exercise(session, ex_id, body.model_dump(exclude_unset=True))


@router.delete("/plan-exercises/{ex_id}")
def delete_plan_exercise(
    ex_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
):
    return admin_plans.delete_plan_exercise(session, ex_id)
