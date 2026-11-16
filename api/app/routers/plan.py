"""H5 计划模板只读 + 按板块展开。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.auth import AuthContext, bind_auth
from app.db import get_session
from app.services import plan_service

router = APIRouter(prefix="/api/plans", tags=["plans"])


class ExpandBody(BaseModel):
    block_id: int = Field(..., ge=1)


@router.get("")
def list_plans(
    type: str | None = Query(default=None, description="framework | fixed"),
    muscle: str | None = Query(default=None),
    level: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _: AuthContext = Depends(bind_auth),
):
    items = plan_service.list_published_plans(
        session,
        template_type=type,
        muscle=muscle,
        level=level,
    )
    return {"items": items, "total": len(items)}


@router.get("/{plan_id}")
def plan_detail(
    plan_id: str,
    session: Session = Depends(get_session),
    _: AuthContext = Depends(bind_auth),
):
    return plan_service.get_plan_detail(session, plan_id)


@router.post("/{plan_id}/expand")
def expand_plan(
    plan_id: str,
    body: ExpandBody,
    session: Session = Depends(get_session),
    _: AuthContext = Depends(bind_auth),
):
    return plan_service.expand_plan_block(session, plan_id, body.block_id)
