"""把一次请求拼成：长期记忆、今天的短期记忆、按需的更早会话、当前输入。"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.brain.memory import format_profile_for_llm
from app.models import ActiveChat, ChatTurn, Profile, utcnow
from app.tenancy import current_user_id

_PAST_CUES = (
    "昨天",
    "前天",
    "上次",
    "之前说",
    "你说过",
    "还是那个",
    "还是上次",
    "上次聊",
    "前两天",
    "前几天",
    "刚才那",
    "上一版",
    "上一张",
)
_SHORT_TERM_BUDGET = 2200
_KEEP_RECENT_TURNS = 8


def _coerce_json(value: Any) -> Any:
    """Postgres 上后补的 card/suggestions 曾是 TEXT。驱动不会解析，原样返回 JSON 字符串。"""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text == "null":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _as_list(value: Any) -> list[Any]:
    parsed = _coerce_json(value)
    return list(parsed) if isinstance(parsed, list) else []


def _as_dict(value: Any) -> dict[str, Any] | None:
    parsed = _coerce_json(value)
    return parsed if isinstance(parsed, dict) else None


def _suggestions(value: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if not label and not prompt:
            continue
        rows.append({"label": label or prompt, "prompt": prompt or label})
    return rows


def refers_to_earlier_chat(text: str) -> bool:
    return any(cue in (text or "") for cue in _PAST_CUES)


def _item_name(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("title") or "")
    return str(getattr(item, "title", "") or "")


def _plan_block(title: str | None, items: list[Any]) -> str:
    lines = [f"计划《{title or '训练'}》"]
    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            lines.append(f"{index}. {item}")
            continue
        meta = item.get("meta") if isinstance(item, dict) else getattr(item, "meta", None) or {}
        selected = item.get("selected", True) if isinstance(item, dict) else getattr(item, "selected", True)
        reps = (meta or {}).get("reps") or ""
        flag = "勾选" if selected else "未勾选"
        extra = f"｜{reps}" if reps else ""
        lines.append(f"{index}. [{flag}] {_item_name(item)}{extra}")
    return "\n".join(lines)


def render_turn(role: str, text: str, card_title: str | None, card_items: list[Any]) -> str:
    who = "用户" if role == "user" else "教练"
    body = (text or "").strip()
    if role == "assistant" and (card_title or card_items):
        plan = _plan_block(card_title, list(card_items or []))
        body = f"{body}\n{plan}" if body else plan
    if not body:
        return ""
    return f"{who}：{body}"


def format_short_term(
    turns: list[dict[str, Any]],
    *,
    draft_title: str | None = None,
    draft_items: list[Any] | None = None,
) -> str:
    """当前对话段里、今天的上下文。最新一张计划用屏幕上的勾选状态。"""
    rendered: list[str] = []
    for turn in turns:
        rendered.append(
            render_turn(
                str(turn.get("role") or "user"),
                str(turn.get("text") or ""),
                turn.get("card_title"),
                list(turn.get("card_items") or []),
            )
        )
    rendered = [line for line in rendered if line]
    if draft_items:
        live = _plan_block(draft_title, draft_items)
        if rendered and rendered[-1].startswith("教练："):
            head = rendered[-1].split("\n计划《", 1)[0]
            rendered[-1] = f"{head}\n{live}" if head.startswith("教练：") else f"教练：\n{live}"
        else:
            rendered.append(f"教练：\n{live}")
    if not rendered:
        return "【短期记忆】\n（本段对话还没有更早的内容）"
    body = "\n".join(rendered)
    if len(body) > _SHORT_TERM_BUDGET and len(rendered) > _KEEP_RECENT_TURNS:
        older = rendered[: -_KEEP_RECENT_TURNS]
        recent = rendered[-_KEEP_RECENT_TURNS :]
        folded = older[-1][:80].replace("\n", " ")
        body = f"更早的本段已折叠，共 {len(older)} 轮。最近一句：{folded}\n" + "\n".join(recent)
    return f"【短期记忆】\n{body}"


def format_past(turns: list[dict[str, Any]]) -> str:
    if not turns:
        return ""
    lines = [
        render_turn(
            str(t.get("role") or "user"),
            str(t.get("text") or ""),
            t.get("card_title"),
            list(t.get("card_items") or []),
        )
        for t in turns
    ]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    clipped = lines[-12:]
    note = f"（共 {len(lines)} 条，这里是最近 {len(clipped)} 条）\n" if len(lines) > len(clipped) else ""
    return "【更早会话】\n" + note + "\n".join(clipped)


def format_current(user_text: str, intent_line: str = "") -> str:
    parts = ["【当前输入】", f"用户本句：{user_text.strip()}"]
    if intent_line:
        parts.append(f"意图：{intent_line}")
    return "\n".join(parts)


def _row_to_dict(row: ChatTurn) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id or "",
        "role": row.role,
        "text": row.text or "",
        "card_title": row.card_title,
        "card_items": [str(item) for item in _as_list(row.card_items) if str(item).strip()],
        "card": _as_dict(row.card),
        "suggestions": _suggestions(row.suggestions),
        "session_day": row.session_day.isoformat(),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _active_chat_q():
    stmt = select(ActiveChat)
    uid = current_user_id()
    if uid is not None:
        stmt = stmt.where(ActiveChat.user_id == uid)
    return stmt


def load_turns(session: Session) -> list[ChatTurn]:
    stmt = select(ChatTurn).order_by(ChatTurn.id)
    uid = current_user_id()
    if uid is not None:
        stmt = stmt.where(ChatTurn.user_id == uid)
    return list(session.exec(stmt).all())


def get_or_create_active_conversation_id(session: Session) -> str:
    """返回当前活跃 conversation_id；没有则新建，并把今天无归属的旧行挂到新段上。"""
    active = session.exec(_active_chat_q().limit(1)).first()
    if active and active.conversation_id:
        return active.conversation_id

    today = date.today()
    orphan_today = [
        row
        for row in load_turns(session)
        if row.session_day == today and not (row.conversation_id or "").strip()
    ]
    cid = str(uuid4())
    for row in orphan_today:
        row.conversation_id = cid
        session.add(row)
    session.add(ActiveChat(user_id=current_user_id(), conversation_id=cid, updated_at=utcnow()))
    session.commit()
    return cid


def start_new_conversation(session: Session) -> str:
    """开新对话段：旧流水保留，活跃指针切到新 id。"""
    cid = str(uuid4())
    active = session.exec(_active_chat_q().limit(1)).first()
    now = utcnow()
    if active:
        active.conversation_id = cid
        active.updated_at = now
        session.add(active)
    else:
        session.add(ActiveChat(user_id=current_user_id(), conversation_id=cid, updated_at=now))
    session.commit()
    return cid


def load_conversation_messages(session: Session, conversation_id: str | None = None) -> dict[str, Any]:
    """当前段里、今天的气泡（给前端渲染）。"""
    cid = conversation_id or get_or_create_active_conversation_id(session)
    today = date.today()
    rows = [
        row
        for row in load_turns(session)
        if row.conversation_id == cid and row.session_day == today
    ]
    messages: list[dict[str, Any]] = []
    for row in rows:
        created = row.created_at.isoformat() if row.created_at else None
        if row.role == "user":
            messages.append(
                {
                    "id": f"db-u-{row.id}",
                    "role": "user",
                    "text": row.text or "",
                    "created_at": created,
                }
            )
            continue
        card = _as_dict(row.card)
        stored_items = [str(item) for item in _as_list(row.card_items) if str(item).strip()]
        if not card and (row.card_title or stored_items):
            items = [
                {
                    "id": f"i{i}",
                    "title": title,
                    "selected": True,
                    "meta": {},
                }
                for i, title in enumerate(stored_items)
            ]
            if items or row.card_title:
                card = {
                    "kind": "card",
                    "card_type": "training_draft",
                    "title": row.card_title or "建议",
                    "status": "draft",
                    "items": items,
                    "actions": ["adopt", "customize"],
                    "meta": {},
                }
        messages.append(
            {
                "id": f"db-a-{row.id}",
                "role": "assistant",
                "text": row.text or "",
                "card": card,
                "suggestions": _suggestions(row.suggestions),
                "created_at": created,
            }
        )
    return {"conversation_id": cid, "messages": messages}


def split_turns(
    session: Session,
    user_text: str,
    history: list[Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """短期记忆 = 今天 + 当前 conversation_id。
    库里没有本段记录时，才回落请求带来的 history（评测用）。
    用户指向「昨天/刚才」时，再带更早会话。
    """
    today = date.today()
    stored = load_turns(session)
    cid = get_or_create_active_conversation_id(session)
    today_rows = [
        row
        for row in stored
        if row.session_day == today and (row.conversation_id or "") == cid
    ]
    if today_rows:
        today_turns = [_row_to_dict(row) for row in today_rows]
    else:
        today_turns = []
        for item in history or []:
            if isinstance(item, dict):
                today_turns.append(
                    {
                        "role": item.get("role") or "user",
                        "text": item.get("text") or "",
                        "card_title": item.get("card_title"),
                        "card_items": list(item.get("card_items") or []),
                    }
                )
            else:
                today_turns.append(
                    {
                        "role": getattr(item, "role", None) or "user",
                        "text": getattr(item, "text", "") or "",
                        "card_title": getattr(item, "card_title", None),
                        "card_items": list(getattr(item, "card_items", None) or []),
                    }
                )

    past: list[dict[str, Any]] = []
    if refers_to_earlier_chat(user_text):
        start = today - timedelta(days=3)
        past = [
            _row_to_dict(row)
            for row in stored
            if start <= row.session_day < today
            or (
                row.session_day == today
                and (row.conversation_id or "") != cid
            )
        ]
    return today_turns, past


def build_intent_context(
    session: Session,
    user_text: str,
    history: list[Any] | None,
    draft_title: str | None,
    draft_items: list[Any] | None,
    profile: Profile | None,
    *,
    include_profile: bool = True,
) -> str:
    today_turns, past = split_turns(session, user_text, history)
    parts: list[str] = []
    if include_profile:
        parts.append("【长期记忆】\n" + format_profile_for_llm(profile))
    past_block = format_past(past)
    if past_block:
        parts.append(past_block)
    parts.append(format_short_term(today_turns, draft_title=draft_title, draft_items=draft_items))
    parts.append(format_current(user_text))
    return "\n\n".join(parts)


def build_worker_context(
    session: Session,
    user_text: str,
    history: list[Any] | None,
    draft_title: str | None,
    draft_items: list[Any] | None,
    long_term_block: str,
    intent_line: str,
) -> str:
    today_turns, past = split_turns(session, user_text, history)
    parts = [long_term_block.strip()]
    past_block = format_past(past)
    if past_block:
        parts.append(past_block)
    parts.append(format_short_term(today_turns, draft_title=draft_title, draft_items=draft_items))
    parts.append(format_current(user_text, intent_line))
    return "\n\n".join(parts) + "\n"


def save_exchange(
    session: Session,
    user_text: str,
    blocks: list[Any],
    *,
    suggestions: list[Any] | None = None,
) -> None:
    """一轮来回追加入当前 conversation，不覆盖旧记录。"""
    today = date.today()
    cid = get_or_create_active_conversation_id(session)
    uid = current_user_id()
    session.add(
        ChatTurn(
            user_id=uid,
            conversation_id=cid,
            session_day=today,
            role="user",
            text=user_text,
        )
    )
    text = ""
    card_title = None
    card_items: list[str] = []
    card_payload: dict[str, Any] | None = None
    for block in blocks:
        kind = block.get("kind") if isinstance(block, dict) else getattr(block, "kind", None)
        if kind == "text" and not text:
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
        if kind == "card" and card_title is None:
            if isinstance(block, dict):
                card_payload = dict(block)
                card_title = block.get("title")
                items = block.get("items") or []
            else:
                card_payload = block.model_dump(mode="json") if hasattr(block, "model_dump") else None
                card_title = getattr(block, "title", None)
                items = getattr(block, "items", []) or []
            card_items = [_item_name(item) for item in items if _item_name(item)]
    tip_rows: list[dict[str, Any]] = []
    for tip in suggestions or []:
        if isinstance(tip, dict):
            tip_rows.append({"label": tip.get("label") or "", "prompt": tip.get("prompt") or ""})
        else:
            tip_rows.append(
                {
                    "label": getattr(tip, "label", "") or "",
                    "prompt": getattr(tip, "prompt", "") or "",
                }
            )
    session.add(
        ChatTurn(
            user_id=uid,
            conversation_id=cid,
            session_day=today,
            role="assistant",
            text=text or "",
            card_title=card_title,
            card_items=card_items,
            card=card_payload,
            suggestions=tip_rows,
        )
    )
    session.commit()
