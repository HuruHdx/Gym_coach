from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.auth import require_token
from app.brain.pipeline import run_chat_pipeline
from app.db import get_session
from app.models import DebugTrace
from app.schemas import AgentReply, ChatRequest

router = APIRouter(prefix="/api", tags=["brain"])


@router.post("/chat", response_model=AgentReply)
async def chat(
    body: ChatRequest,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    return await run_chat_pipeline(
        session,
        body.text,
        draft_items=body.draft_items,
        draft_title=body.draft_title,
    )


@router.get("/debug/traces")
def list_traces(
    limit: int = 20,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    rows = session.exec(select(DebugTrace).order_by(DebugTrace.id.desc()).limit(limit)).all()
    return [
        {"id": r.id, "created_at": r.created_at, "user_text": r.user_text, "payload": r.payload}
        for r in rows
    ]


@router.get("/debug/traces/{trace_id}")
def get_trace(
    trace_id: int,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    row = session.get(DebugTrace, trace_id)
    if not row:
        return {"error": "not found"}
    return {"id": row.id, "created_at": row.created_at, "user_text": row.user_text, "payload": row.payload}
