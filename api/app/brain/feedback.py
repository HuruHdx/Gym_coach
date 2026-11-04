"""聊天点赞/点踩：拼快照、落 FeedbackEvent、供 inbox 导出。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import ActiveChat, ChatTurn, DebugTrace, FeedbackEvent, utcnow
from app.schemas import FEEDBACK_TAGS, FeedbackRequest
from app.tenancy import current_user_id, get_current_profile

_ALLOWED_TAGS = set(FEEDBACK_TAGS)


def _text_from_blocks(blocks: list[Any] | None) -> str:
    for block in blocks or []:
        if isinstance(block, dict) and block.get("kind") == "text" and block.get("text"):
            return str(block["text"])
    return ""


def _intent_summary(intent: dict[str, Any] | None) -> dict[str, Any]:
    data = intent or {}
    params = data.get("params") or {}
    return {
        "agent": params.get("agent"),
        "topic": params.get("topic"),
        "domain": params.get("domain"),
        "muscles": list(data.get("muscles") or []),
        "focus_exercises": list(params.get("focus_exercises") or []),
        "rewrite": params.get("rewrite") or "",
    }


def _profile_brief(profile: Profile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    goal = profile.goal.value if hasattr(profile.goal, "value") else str(profile.goal)
    exp = profile.experience.value if hasattr(profile.experience, "value") else str(profile.experience)
    return {
        "goal": goal,
        "experience": exp,
        "weight_kg": profile.weight_kg,
        "days_per_week": profile.days_per_week,
        "injuries": list(profile.injuries or []),
    }


def _history_from_turns(turns: list[ChatTurn], *, exclude_ids: set[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for turn in turns:
        if turn.id in exclude_ids:
            continue
        item: dict[str, Any] = {"role": turn.role, "text": turn.text or ""}
        if turn.role == "assistant" and (turn.card_title or turn.card_items):
            item["card_title"] = turn.card_title
            item["card_items"] = list(turn.card_items or [])
        rows.append(item)
    return rows[-12:]


def _card_from_turn(turn: ChatTurn | None) -> dict[str, Any] | None:
    if turn is None:
        return None
    if isinstance(turn.card, dict) and turn.card:
        return turn.card
    if turn.card_title or turn.card_items:
        return {
            "title": turn.card_title,
            "items": [{"title": name} for name in (turn.card_items or [])],
        }
    return None


def build_snapshot(
    session: Session,
    *,
    trace: DebugTrace | None,
    assistant_turn: ChatTurn | None,
    question: str,
    answer: str,
) -> dict[str, Any]:
    payload = dict(trace.payload or {}) if trace is not None else {}
    intent_raw = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
    grounding = payload.get("grounding") if isinstance(payload.get("grounding"), dict) else {}
    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    blocks = payload.get("blocks") if isinstance(payload.get("blocks"), list) else []
    suggestions = payload.get("suggestions")
    if not suggestions and isinstance(grounding.get("suggestions"), list):
        suggestions = grounding.get("suggestions")

    profile = get_current_profile(session)
    conversation_id = ""
    history: list[dict[str, Any]] = []
    draft_title = None
    draft_items: list[Any] = []
    has_card = False

    if assistant_turn is not None:
        conversation_id = assistant_turn.conversation_id or ""
        card = _card_from_turn(assistant_turn)
        if card:
            has_card = True
            draft_title = card.get("title") or assistant_turn.card_title
            raw_items = card.get("items") if isinstance(card.get("items"), list) else []
            if raw_items:
                draft_items = raw_items
            elif assistant_turn.card_items:
                draft_items = [
                    {"title": name, "selected": True, "meta": {}} for name in assistant_turn.card_items
                ]
        prior = list(
            session.exec(
                select(ChatTurn)
                .where(ChatTurn.conversation_id == conversation_id)
                .where(ChatTurn.id < (assistant_turn.id or 0))
                .order_by(ChatTurn.id)
            ).all()
        )
        history = _history_from_turns(prior, exclude_ids=set())
        if not answer:
            answer = assistant_turn.text or ""
        if not suggestions and assistant_turn.suggestions:
            suggestions = list(assistant_turn.suggestions)
    elif conversation_id == "":
        aq = select(ActiveChat)
        uid = current_user_id()
        if uid is not None:
            aq = aq.where(ActiveChat.user_id == uid)
        active = session.exec(aq.limit(1)).first()
        conversation_id = (active.conversation_id if active else "") or ""

    if not answer:
        answer = _text_from_blocks(blocks)

    return {
        "intent": _intent_summary(intent_raw if isinstance(intent_raw, dict) else {}),
        "route": graph.get("route"),
        "branch": grounding.get("branch") or graph.get("route"),
        "kb": grounding.get("kb") or {},
        "citations": list(grounding.get("citations") or []),
        "history": history,
        "draft_title": draft_title,
        "draft_items": draft_items,
        "profile": _profile_brief(profile),
        "suggestions": list(suggestions or []),
        "has_card": has_card or any(isinstance(b, dict) and b.get("kind") == "card" for b in blocks),
        "question": question,
        "answer": answer,
    }


def _find_existing(
    session: Session,
    *,
    trace_id: int | None,
    assistant_turn_id: int | None,
) -> FeedbackEvent | None:
    if trace_id is not None:
        row = session.exec(select(FeedbackEvent).where(FeedbackEvent.trace_id == trace_id)).first()
        if row is not None:
            return row
    if assistant_turn_id is not None:
        return session.exec(
            select(FeedbackEvent).where(FeedbackEvent.assistant_turn_id == assistant_turn_id)
        ).first()
    return None


def _resolve_context(
    session: Session, body: FeedbackRequest
) -> tuple[DebugTrace | None, ChatTurn | None, str, str, str]:
    if body.trace_id is None and body.assistant_turn_id is None:
        raise HTTPException(status_code=400, detail="trace_id 或 assistant_turn_id 至少提供一个")

    trace: DebugTrace | None = None
    if body.trace_id is not None:
        trace = session.get(DebugTrace, body.trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace not found")

    assistant_turn: ChatTurn | None = None
    if body.assistant_turn_id is not None:
        assistant_turn = session.get(ChatTurn, body.assistant_turn_id)
        if assistant_turn is None or assistant_turn.role != "assistant":
            raise HTTPException(status_code=404, detail="assistant turn not found")

    question = (trace.user_text if trace is not None else "") or ""
    answer = ""
    conversation_id = ""

    if assistant_turn is not None:
        conversation_id = assistant_turn.conversation_id or ""
        answer = assistant_turn.text or ""
        if not question:
            prior = session.exec(
                select(ChatTurn)
                .where(ChatTurn.conversation_id == conversation_id)
                .where(ChatTurn.id < (assistant_turn.id or 0))
                .where(ChatTurn.role == "user")
                .order_by(ChatTurn.id.desc())
            ).first()
            question = (prior.text if prior else "") or ""
    elif trace is not None:
        answer = _text_from_blocks((trace.payload or {}).get("blocks"))
        aq = select(ActiveChat)
        uid = current_user_id()
        if uid is not None:
            aq = aq.where(ActiveChat.user_id == uid)
        active = session.exec(aq.limit(1)).first()
        conversation_id = (active.conversation_id if active else "") or ""
        # 尽量挂上刚写下的助手轮
        if conversation_id:
            recent = session.exec(
                select(ChatTurn)
                .where(ChatTurn.conversation_id == conversation_id)
                .where(ChatTurn.role == "assistant")
                .order_by(ChatTurn.id.desc())
            ).first()
            if recent is not None and (recent.text or "") == answer:
                assistant_turn = recent

    return trace, assistant_turn, conversation_id, question, answer


def submit_feedback(session: Session, body: FeedbackRequest) -> FeedbackEvent:
    tags = [t for t in body.tags if isinstance(t, str) and t in _ALLOWED_TAGS]
    note = (body.note or "").strip()
    if body.rating == "down" and not tags:
        raise HTTPException(status_code=400, detail="点踩至少选一个标签")
    if body.rating == "up":
        tags = []

    trace, assistant_turn, conversation_id, question, answer = _resolve_context(session, body)
    snapshot = build_snapshot(
        session,
        trace=trace,
        assistant_turn=assistant_turn,
        question=question,
        answer=answer,
    )

    existing = _find_existing(
        session,
        trace_id=body.trace_id or (trace.id if trace else None),
        assistant_turn_id=body.assistant_turn_id
        or (assistant_turn.id if assistant_turn is not None else None),
    )
    if existing is not None:
        existing.rating = body.rating
        existing.tags = tags
        existing.note = note
        existing.question = question
        existing.answer = answer or snapshot.get("answer") or ""
        existing.snapshot = snapshot
        existing.conversation_id = conversation_id or existing.conversation_id
        if trace is not None:
            existing.trace_id = trace.id
        if assistant_turn is not None:
            existing.assistant_turn_id = assistant_turn.id
        # 改踩改赞后重新进入待导出
        existing.export_status = "pending" if body.rating == "down" else "discarded"
        existing.created_at = utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    row = FeedbackEvent(
        rating=body.rating,
        tags=tags,
        note=note,
        conversation_id=conversation_id,
        assistant_turn_id=assistant_turn.id if assistant_turn is not None else None,
        trace_id=trace.id if trace is not None else body.trace_id,
        question=question,
        answer=answer or str(snapshot.get("answer") or ""),
        snapshot=snapshot,
        export_status="pending" if body.rating == "down" else "discarded",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_feedback(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[FeedbackEvent]:
    stmt = select(FeedbackEvent).order_by(FeedbackEvent.id.desc()).limit(max(1, min(limit, 200)))
    if status:
        stmt = (
            select(FeedbackEvent)
            .where(FeedbackEvent.export_status == status)
            .order_by(FeedbackEvent.id.desc())
            .limit(max(1, min(limit, 200)))
        )
    return list(session.exec(stmt).all())
