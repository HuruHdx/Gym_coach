from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.auth import require_token
from app.brain.memory_context import (
    get_or_create_active_conversation_id,
    load_conversation_messages,
    start_new_conversation,
)
from app.brain.pipeline import run_chat_pipeline
from app.db import get_session
from app.brain.feedback import list_feedback, submit_feedback
from app.models import DebugTrace, Experience, Goal, Profile
from app.schemas import AgentReply, ChatRequest, EvalQaRequest, FeedbackOut, FeedbackRequest

router = APIRouter(prefix="/api", tags=["brain"])


@router.post("/chat", response_model=AgentReply)
async def chat(
    body: ChatRequest,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    # 确保有活跃段；短期记忆以库为准，history 仅作评测回落
    get_or_create_active_conversation_id(session)
    return await run_chat_pipeline(
        session,
        body.text,
        draft_items=body.draft_items,
        draft_title=body.draft_title,
        history=body.history,
    )


@router.get("/chat/conversation")
def get_conversation(
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    """当前活跃对话段（今天）的气泡，供前端进页渲染。"""
    return load_conversation_messages(session)


@router.post("/chat/conversation")
def new_conversation(
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    """新对话：开新 conversation_id，旧流水保留。"""
    cid = start_new_conversation(session)
    return {"conversation_id": cid, "messages": []}


_GOALS = {"增肌": Goal.BULK, "减脂": Goal.CUT, "力量": Goal.STRENGTH, "塑形": Goal.SHAPE}
_LEVELS = {"新手": Experience.NOVICE, "进阶": Experience.INTERMEDIATE, "老炮": Experience.ADVANCED}


def _eval_profile(body: EvalQaRequest) -> Profile:
    raw = body.profile
    if raw is None:
        return Profile(goal=Goal.BULK, experience=Experience.NOVICE, weight_kg=70, days_per_week=4, injuries=[])
    return Profile(
        goal=_GOALS.get(raw.goal, Goal.BULK),
        experience=_LEVELS.get(raw.experience, Experience.NOVICE),
        weight_kg=raw.weight_kg,
        days_per_week=raw.days_per_week,
        injuries=list(raw.injuries or []),
    )


def _eval_body(state: dict) -> dict:
    grounding = state.get("grounding") or {}
    kb = grounding.get("kb") or {}
    search = grounding.get("search") or {}
    blocks = state.get("blocks") or []
    answer = ""
    for block in blocks:
        if block.get("kind") == "text" and block.get("text"):
            answer = str(block["text"])
            break
    if not answer:
        answer = str(grounding.get("answer") or "")
    intent = state.get("intent") or {}
    params = intent.get("params") or {}
    focus = params.get("focus_exercises") or []
    return {
        "answer": answer,
        "route": state.get("route"),
        "branch": grounding.get("branch") or state.get("route"),
        "model_called": bool(grounding.get("model_called")),
        "suggestions": grounding.get("suggestions") or state.get("suggestions") or [],
        "intent": {
            "agent": params.get("agent"),
            "topic": params.get("topic"),
            "domain": params.get("domain"),
            "muscles": intent.get("muscles") or [],
            "focus_exercises": focus or [],
            "qa_kind": params.get("qa_kind"),
            "rewrite": params.get("rewrite") or "",
        },
        "stats": state.get("stats") or {
            "queried": False,
            "filter": {"muscles": intent.get("muscles") or [], "names": []},
            "tool_calls": [],
            "hits": [],
        },
        "kb": {
            "queried": bool(kb.get("queried")),
            "hit": bool(kb.get("hit")),
            "top_score": float(kb.get("top_score") or 0),
            "margin": float(kb.get("margin") or 0),
            "reason": kb.get("reason") or "not_queried",
            "hits": kb.get("hits") or [],
            "near_miss": kb.get("near_miss") or [],
        },
        "search": {
            "called": bool(search.get("called")),
            "query": search.get("query"),
            "results": search.get("results") or [],
        },
        "citations": list(grounding.get("citations") or []),
    }


@router.post("/eval/qa")
async def eval_qa(body: EvalQaRequest, _: str = Depends(require_token)):
    """评测专用。不写对话、不改记忆、不写 DebugTrace。"""
    from sqlmodel import SQLModel, Session, create_engine

    from app.brain.graph import invoke_chat_graph

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_eval_profile(body))
        session.commit()
        state = await invoke_chat_graph(
            session,
            user_text=body.question,
            draft_title=body.draft_title,
            draft_items=body.draft_items,
            history=body.history,
            eval_mode=True,
            intent_only=body.mode == "intent",
            search_mode=body.search_mode,
            search_fixture=[item.model_dump() for item in body.search_fixture],
            stats_fixture=[item.model_dump() for item in body.stats_fixture],
        )
        from app.brain.graph import _intent
        from app.brain.knowledge_reply import collect_training_stats

        _text, stats = collect_training_stats(
            session,
            _intent(state.get("intent") or {}),
            body.question,
            stats_fixture=[item.model_dump() for item in body.stats_fixture],
        )
        state = {**state, "stats": stats}
    return _eval_body(state)


@router.post("/feedback", response_model=FeedbackOut)
def post_feedback(
    body: FeedbackRequest,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    """聊天气泡点赞/点踩。差评写入快照，供导出 eval/inbox。"""
    row = submit_feedback(session, body)
    return FeedbackOut(
        id=row.id or 0,
        rating=row.rating,  # type: ignore[arg-type]
        tags=list(row.tags or []),
        note=row.note or "",
        conversation_id=row.conversation_id or "",
        assistant_turn_id=row.assistant_turn_id,
        trace_id=row.trace_id,
        question=row.question or "",
        answer=row.answer or "",
        export_status=row.export_status or "pending",
        created_at=row.created_at,
    )


@router.get("/feedback", response_model=list[FeedbackOut])
def get_feedback(
    status: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    rows = list_feedback(session, status=status, limit=limit)
    return [
        FeedbackOut(
            id=row.id or 0,
            rating=row.rating,  # type: ignore[arg-type]
            tags=list(row.tags or []),
            note=row.note or "",
            conversation_id=row.conversation_id or "",
            assistant_turn_id=row.assistant_turn_id,
            trace_id=row.trace_id,
            question=row.question or "",
            answer=row.answer or "",
            export_status=row.export_status or "pending",
            created_at=row.created_at,
        )
        for row in rows
    ]


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
