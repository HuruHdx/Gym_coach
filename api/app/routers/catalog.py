"""C 端动作库只读接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.auth import AuthContext, bind_auth
from app.db import get_session
from app.services import public_catalog

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


@router.get("")
def list_exercises(
    q: str | None = Query(default=None),
    muscle: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=60),
    session: Session = Depends(get_session),
    _: AuthContext = Depends(bind_auth),
):
    return public_catalog.list_public_exercises(
        session,
        q=q,
        muscle=muscle,
        page=page,
        page_size=page_size,
    )


@router.get("/resolve")
def resolve_exercises(
    names: str = Query(default="", description="逗号分隔的动作名"),
    session: Session = Depends(get_session),
    _: AuthContext = Depends(bind_auth),
):
    parts = [p.strip() for p in names.split(",") if p.strip()]
    # 去重但保序
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    resolved = public_catalog.resolve_by_names(session, seen[:40])
    return {"items": resolved}


@router.get("/{exercise_id}")
def get_exercise(
    exercise_id: str,
    session: Session = Depends(get_session),
    _: AuthContext = Depends(bind_auth),
):
    detail = public_catalog.get_public_exercise(session, exercise_id)
    if not detail:
        raise HTTPException(status_code=404, detail="动作不存在")
    return detail
