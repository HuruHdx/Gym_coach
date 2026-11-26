"""Admin AI Ops：未命中池 + 差评收件箱。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.auth import require_admin
from app.db import get_session
from app.services import ai_ops_service

router = APIRouter(prefix="/api/admin/ai-ops", tags=["admin-ai-ops"])


class MissDiagnoseIn(BaseModel):
    norm_query: str = Field(min_length=1, max_length=120)
    display_query: str | None = Field(default=None, max_length=200)
    examples: list[str] = Field(default_factory=list, max_length=5)


class MissBindIn(BaseModel):
    norm_query: str = Field(min_length=1, max_length=120)
    exercise_id: str = Field(min_length=1, max_length=32)
    alias: str | None = Field(default=None, max_length=120)


class MissResolveIn(BaseModel):
    norm_query: str = Field(min_length=1, max_length=120)
    status: Literal["created_sku", "ignored"]
    bound_exercise_id: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=500)


class FeedbackExportIn(BaseModel):
    write_file: bool = True
    format: Literal["auto", "single", "thread"] = "auto"


class AliasIn(BaseModel):
    exercise_id: str = Field(min_length=1, max_length=32)
    alias: str = Field(min_length=1, max_length=120)


@router.get("/misses")
def get_misses(
    status: str = Query(default="pending"),
    limit_traces: int = Query(default=300, ge=50, le=1000),
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    items = ai_ops_service.list_missed_queries(session, status=status, limit_traces=limit_traces)
    return {"items": items, "total": len(items)}


@router.post("/misses/diagnose")
async def post_miss_diagnose(
    body: MissDiagnoseIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    return await ai_ops_service.diagnose_missed_query(
        session,
        norm_query=body.norm_query,
        display_query=body.display_query,
        examples=body.examples,
    )


@router.post("/misses/bind-alias")
def post_miss_bind(
    body: MissBindIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    return ai_ops_service.bind_miss_to_alias(
        session,
        norm_query=body.norm_query,
        exercise_id=body.exercise_id,
        alias=body.alias,
    )


@router.post("/misses/resolve")
def post_miss_resolve(
    body: MissResolveIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    return ai_ops_service.resolve_miss(
        session,
        norm_query=body.norm_query,
        status=body.status,
        bound_exercise_id=body.bound_exercise_id,
        note=body.note,
    )


@router.get("/plan-gaps")
def get_plan_gaps(
    limit_traces: int = Query(default=400, ge=50, le=1000),
    top_n: int = Query(default=8, ge=1, le=20),
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    items = ai_ops_service.list_plan_recommend_gaps(
        session, limit_traces=limit_traces, top_n=top_n
    )
    return {"items": items, "total": len(items)}


@router.post("/aliases")
def post_alias(
    body: AliasIn,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    """工坊口播词 / 手动补别名：落库并热重载。"""
    return ai_ops_service.ensure_exercise_alias(
        session, exercise_id=body.exercise_id, alias=body.alias
    )


@router.get("/feedbacks")
def get_feedbacks(
    status: str | None = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    items = ai_ops_service.list_feedbacks(session, status=status, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/feedbacks/{feedback_id}/diagnose")
async def post_feedback_diagnose(
    feedback_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    return await ai_ops_service.diagnose_feedback(session, feedback_id)


@router.post("/feedbacks/{feedback_id}/export")
def post_feedback_export(
    feedback_id: int,
    body: FeedbackExportIn | None = None,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    payload = body or FeedbackExportIn()
    return ai_ops_service.export_feedback_case(
        session,
        feedback_id,
        write_file=payload.write_file,
        format=payload.format,
    )


@router.post("/feedbacks/{feedback_id}/discard")
def post_feedback_discard(
    feedback_id: int,
    session: Session = Depends(get_session),
    _: object = Depends(require_admin),
) -> dict[str, Any]:
    return ai_ops_service.discard_feedback(session, feedback_id)
