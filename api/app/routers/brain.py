from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.auth import AuthContext, bind_auth
from app.brain.memory_context import (
    get_or_create_active_conversation_id,
    load_conversation_messages,
    start_new_conversation,
)
from app.brain.pipeline import run_chat_pipeline
from app.db import get_session
from app.brain.feedback import list_feedback, submit_feedback
from app.models import DebugTrace, Experience, Goal, Profile
from app.schemas import (
    AgentReply,
    ChatDraftItem,
    ChatRequest,
    EvalQaRequest,
    EvalThreadOut,
    EvalThreadRequest,
    EvalTurnOut,
    FeedbackOut,
    FeedbackRequest,
)

router = APIRouter(prefix="/api", tags=["brain"])


@router.post("/chat", response_model=AgentReply)
async def chat(
    body: ChatRequest,
    session: Session = Depends(get_session),
    _: AuthContext = Depends(bind_auth),
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
    _: AuthContext = Depends(bind_auth),
):
    """当前活跃对话段（今天）的气泡，供前端进页渲染。"""
    return load_conversation_messages(session)


@router.post("/chat/conversation")
def new_conversation(
    session: Session = Depends(get_session),
    _: AuthContext = Depends(bind_auth),
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
async def eval_qa(body: EvalQaRequest, _: AuthContext = Depends(bind_auth)):
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


def _turn_cards(state: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    """从这一轮的 blocks 里取出草稿卡。这张卡就是「前端屏幕上看到的东西」。"""
    for block in state.get("blocks") or []:
        if block.get("kind") == "card":
            return block.get("title"), list(block.get("items") or [])
    return None, []


def _to_draft_items(items: list[dict[str, Any]]) -> list[ChatDraftItem]:
    """卡片 → 下一轮的 draft_items。只带选中项，和前端点「采纳」的语义一致。"""
    out: list[ChatDraftItem] = []
    for item in items:
        if not item.get("selected", True):
            continue
        out.append(
            ChatDraftItem(
                title=str(item.get("title") or ""),
                selected=True,
                meta=dict(item.get("meta") or {}),
            )
        )
    return out


def _thread_turn(index: int, text: str, state: dict[str, Any]) -> EvalTurnOut:
    intent = state.get("intent") or {}
    params = intent.get("params") or {}
    title, items = _turn_cards(state)
    dropped = []
    for block in state.get("blocks") or []:
        if block.get("kind") == "card":
            dropped = list((block.get("meta") or {}).get("dropped") or [])
    text_block = ""
    for block in state.get("blocks") or []:
        if block.get("kind") == "text" and block.get("text"):
            text_block = str(block["text"])
            break
    card_items_meta = [
        {
            "title": str(item.get("title") or ""),
            "selected": bool(item.get("selected", True)),
            "meta": dict(item.get("meta") or {}),
        }
        for item in items
    ]
    return EvalTurnOut(
        index=index,
        text=text,
        route=str(state.get("route") or ""),
        topic=params.get("topic"),
        domain=params.get("domain"),
        draft_relation=params.get("draft_relation"),
        session_target=params.get("session_target"),
        card_title=title,
        card_items=[str(i.get("title") or "") for i in items],
        card_items_meta=card_items_meta,
        card_item_count=len(items),
        selected_count=sum(1 for i in items if i.get("selected", True)),
        dropped=dropped,
        text_block=text_block,
        suggestions=list(state.get("suggestions") or []),
        draft_title=title,
    )


@router.post("/eval/thread", response_model=EvalThreadOut)
async def eval_thread(body: EvalThreadRequest, _: AuthContext = Depends(bind_auth)):
    """
    长对话评测：整条对话在同一台内存库里顺序跑。

    和 /eval/qa 的关键区别 —— 上一轮产出的草稿会自动变成下一轮的 draft_items，
    复刻「模型给一版 → 用户在这版上改」的真实链路。
    手工在 YAML 里维护 history 做不到这一点：草稿内容只有模型自己知道。

    默认走**真实排课链路**（draft_plan → validate，会真的出卡）；只有显式传
    short_circuit=True 时才复用 /eval/qa 的「只回路由说明」捷径 —— 那条捷径不出卡，
    长对话的改稿/伤痛/采纳断言全部无从谈起。
    """
    from sqlmodel import SQLModel, Session, create_engine

    from app.brain.graph import invoke_chat_graph

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    out = EvalThreadOut(name=body.name)

    with Session(engine) as session:
        session.add(_eval_profile_like(body))
        session.commit()

        history: list[dict[str, Any]] = []
        draft_items: list[ChatDraftItem] = []
        draft_title: str | None = None

        for index, turn in enumerate(body.turns):
            try:
                state = await invoke_chat_graph(
                    session,
                    user_text=turn.text,
                    draft_title=draft_title,
                    draft_items=draft_items,
                    history=history,
                    eval_mode=body.short_circuit,
                    search_mode=body.search_mode,
                    search_fixture=[item.model_dump() for item in body.search_fixture],
                    stats_fixture=[item.model_dump() for item in body.stats_fixture],
                )
            except Exception as exc:  # noqa: BLE001
                out.error = f"第 {index + 1} 轮失败：{exc}"
                return out

            out.turns.append(_thread_turn(index, turn.text, state))

            # 累积对话摘要（给下一轮当短期记忆）
            title, items = _turn_cards(state)
            answer = ""
            for block in state.get("blocks") or []:
                if block.get("kind") == "text" and block.get("text"):
                    answer = str(block["text"])
                    break
            history.append({"role": "user", "text": turn.text})
            history.append(
                {
                    "role": "assistant",
                    "text": answer,
                    "card_title": title,
                    "card_items": [str(i.get("title") or "") for i in items],
                }
            )

            # 这一轮出了新卡 → 变成下一轮的草稿；没出卡 → 沿用旧草稿（改稿语义）
            if title:
                draft_title = title
                draft_items = _to_draft_items(items)

        # 可选：把最后一张草稿真的落成记录，验证「采纳 → 打卡 → 回写」
        if body.adopt_after is not None and not draft_items:
            # 没有草稿多半是链路走了短路 / 整条对话没出卡，明确报出来而不是静默跳过
            out.error = "采纳失败：整条对话没有产出可采纳的卡片"
        if body.adopt_after is not None and draft_items:
            from app.schemas import AdoptRequest, DraftItemIn
            from app.services import session_service as svc

            try:
                adopted = svc.adopt_draft(
                    session,
                    AdoptRequest(
                        title=draft_title or "今日计划",
                        items=[
                            DraftItemIn(title=i.title, meta=i.meta, selected=True)
                            for i in draft_items
                        ],
                        replace_today=True,
                    ),
                )
                out.adopted = {
                    "session_id": adopted.id,
                    "status": adopted.status,
                    "set_count": len(adopted.sets),
                    "exercises": sorted({s.exercise_name for s in adopted.sets}),
                    "progress": adopted.progress,
                }
            except Exception as exc:  # noqa: BLE001
                out.error = f"采纳失败：{exc}"

    return out


def _eval_profile_like(body: EvalThreadRequest) -> Profile:
    """thread 请求只带 profile 简表，这里复用 /eval/qa 的映射。"""
    raw = body.profile
    if raw is None:
        return Profile(
            goal=Goal.BULK, experience=Experience.NOVICE, weight_kg=70, days_per_week=4, injuries=[]
        )
    return Profile(
        goal=_GOALS.get(raw.goal, Goal.BULK),
        experience=_LEVELS.get(raw.experience, Experience.NOVICE),
        weight_kg=raw.weight_kg,
        days_per_week=raw.days_per_week,
        injuries=list(raw.injuries or []),
    )


@router.post("/feedback", response_model=FeedbackOut)
def post_feedback(
    body: FeedbackRequest,
    session: Session = Depends(get_session),
    _: AuthContext = Depends(bind_auth),
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
    _: AuthContext = Depends(bind_auth),
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
    _: AuthContext = Depends(bind_auth),
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
    _: AuthContext = Depends(bind_auth),
):
    row = session.get(DebugTrace, trace_id)
    if not row:
        return {"error": "not found"}
    return {"id": row.id, "created_at": row.created_at, "user_text": row.user_text, "payload": row.payload}
