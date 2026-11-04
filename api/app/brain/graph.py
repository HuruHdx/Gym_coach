"""Chat agent graph.

rewrite_intent →
  coach_plan + not ready → clarify
  coach_plan + ready → assemble_memory → draft_plan → validate
  coach_chat → ground_knowledge → knowledge_reply（动作问答）或 chat_reply（采纳 / 记忆）
  nutrition → nutrition_reply
"""

from __future__ import annotations

import operator
import os
import time
from contextvars import ContextVar
from typing import Annotated, Any, Literal

from langgraph.graph import END, StateGraph
from sqlmodel import Session, select
from typing_extensions import TypedDict

from app.tenancy import get_current_profile

from app.brain.intent_rewrite import (
    build_clarification,
    generate_clarification,
    needs_clarification,
    rewrite_intent,
)
from app.brain.knowledge_reply import knowledge_reply_node
from app.brain.llm import get_llm
from app.brain.memory import (
    Intent,
    apply_profile_defaults,
    assemble_memory,
    draft_title_for_intent,
    format_intent_for_prompt,
)
from app.brain.pipeline import (
    _normalize_card_title,
    _select_all_items,
    _trim_to_request,
)
from app.brain.memory import build_profile_summary
from app.brain.validate import validate_and_build_blocks
from app.config import settings
from app.models import Profile

_db: ContextVar[Session | None] = ContextVar("chat_graph_db", default=None)


class ChatState(TypedDict, total=False):
    user_text: str
    history: list[dict[str, Any]]
    draft_title: str | None
    draft_items: list[dict[str, Any]]
    intent: dict[str, Any]
    route: Literal["clarify", "plan", "chat", "nutrition"]
    injuries: list[str]
    suggestions: list[dict[str, str]]
    memory: dict[str, Any]
    prompt_user: str
    raw: dict[str, Any]
    parse_ok: bool
    error: str | None
    blocks: list[dict[str, Any]]
    grounding: dict[str, Any]
    eval_mode: bool
    intent_only: bool
    search_mode: str
    search_fixture: list[dict[str, Any]]
    stats_fixture: list[dict[str, Any]]
    stats: dict[str, Any]
    steps: Annotated[list[dict[str, Any]], operator.add]


def _session() -> Session:
    session = _db.get()
    if session is None:
        raise RuntimeError("chat graph has no database session")
    return session


def _intent(data: dict[str, Any]) -> Intent:
    return Intent(
        expert=data.get("expert") or "general",
        muscles=list(data.get("muscles") or []),
        raw=data.get("raw") or "",
        params=dict(data.get("params") or {}),
    )


def _step(node: str, started: float, **output: Any) -> dict[str, Any]:
    return {
        "steps": [
            {
                "node": node,
                "ms": int((time.perf_counter() - started) * 1000),
                **output,
            }
        ]
    }


def _pick_route(intent: Intent, has_draft: bool) -> Literal["clarify", "plan", "chat", "nutrition"]:
    params = intent.params or {}
    topic = params.get("topic")
    domain = params.get("domain")
    # 口头说采纳 / 开始训练：不新开课。真正采纳只在卡片按钮上。
    if params.get("adopt_hint"):
        return "chat"
    if topic == "plan":
        if domain == "nutrition":
            return "nutrition"
        if has_draft and is_draft_revision_safe(intent):
            return "plan"
        return "clarify" if needs_clarification(intent, has_draft=has_draft) else "plan"
    if topic in ("qa", "chitchat"):
        return "chat"
    # 没有 topic：退回旧逻辑
    agent = params.get("agent")
    if agent == "nutrition" or intent.expert == "nutrition":
        return "nutrition"
    if has_draft and is_draft_revision_safe(intent):
        return "plan"
    if agent == "coach_chat" or intent.expert == "chat":
        return "chat"
    if needs_clarification(intent, has_draft=has_draft):
        return "clarify"
    return "plan"


def is_draft_revision_safe(intent: Intent) -> bool:
    from app.brain.intent_rewrite import is_draft_revision

    return is_draft_revision(intent.raw, intent.params)


async def rewrite_intent_node(state: ChatState) -> dict[str, Any]:
    started = time.perf_counter()
    profile = get_current_profile(_session())
    from app.brain.memory_context import build_intent_context

    context = build_intent_context(
        _session(),
        state["user_text"],
        state.get("history"),
        state.get("draft_title"),
        state.get("draft_items"),
        profile,
        include_profile=False,
    )
    intent = apply_profile_defaults(
        await rewrite_intent(
            state["user_text"],
            profile=profile,
            history=state.get("history") or [],
            context=context,
            draft_title=state.get("draft_title"),
        ),
        profile,
    )
    has_draft = bool(state.get("draft_items"))
    formatted = format_intent_for_prompt(intent, profile=profile)
    route = _pick_route(intent, has_draft=has_draft)
    payload = {
        "expert": intent.expert,
        "muscles": list(intent.muscles),
        "raw": intent.raw,
        "params": dict(intent.params or {}),
        "formatted": formatted,
    }
    return {
        "intent": payload,
        "route": route,
        "injuries": list(profile.injuries) if profile else [],
        **_step(
            node="rewrite_intent",
            started=started,
            route=route,
            agent=intent.params.get("agent"),
            ready=intent.params.get("ready"),
            intent=formatted,
        ),
    }


async def clarify_node(state: ChatState) -> dict[str, Any]:
    started = time.perf_counter()
    intent = _intent(state["intent"])
    text, options = build_clarification(intent)
    # 意图空白：话术由模型按原话写，不走写死文案
    if not text:
        profile = get_current_profile(_session())
        brief = ""
        if profile is not None:
            from app.brain.memory_context import build_intent_context

            brief = build_intent_context(
                _session(),
                state["user_text"],
                state.get("history"),
                state.get("draft_title"),
                state.get("draft_items"),
                profile,
            )
            brief += f"\n要确认的点：{intent.params.get('tension', {}).get('kind') if isinstance(intent.params.get('tension'), dict) else ''}"
        text, options = await generate_clarification(intent, brief)
    suggestions = [{"label": o["label"], "prompt": o["prompt"]} for o in options]
    blocks = [{"kind": "text", "text": text}]
    return {
        "suggestions": suggestions,
        "blocks": blocks,
        **_step(
            "clarify",
            started,
            text=text,
            suggestions=[s["label"] for s in suggestions],
        ),
    }


async def assemble_memory_node(state: ChatState) -> dict[str, Any]:
    started = time.perf_counter()
    session = _session()
    profile = get_current_profile(session)
    intent = _intent(state["intent"])
    memory = assemble_memory(session, intent, profile)
    from app.brain.memory_context import build_worker_context

    prompt = build_worker_context(
        session,
        state["user_text"],
        state.get("history"),
        state.get("draft_title"),
        state.get("draft_items"),
        memory.as_prompt_block(),
        state["intent"].get("formatted") or "",
    )
    packed = {
        "profile_summary": memory.profile_summary,
        "derived": memory.derived_summaries,
        "logs": memory.recent_logs,
        "token_estimate": memory.token_estimate,
    }
    return {
        "memory": packed,
        "prompt_user": prompt,
        **_step(
            "assemble_memory",
            started,
            token_estimate=memory.token_estimate,
            derived=len(memory.derived_summaries),
            logs=len(memory.recent_logs),
        ),
    }


async def draft_plan_node(state: ChatState) -> dict[str, Any]:
    started = time.perf_counter()
    parse_ok = True
    error: str | None = None
    tool_trace: list[dict[str, Any]] = []
    try:
        from app.brain.plan_loop import draft_plan_with_tools
        from app.brain.tools import build_tool_context

        session = _session()
        profile = get_current_profile(session)
        intent = _intent(state["intent"])
        ctx = build_tool_context(session, intent, profile)
        raw, tool_trace = await draft_plan_with_tools(
            get_llm(),
            state.get("prompt_user") or "",
            ctx,
        )
    except Exception as exc:  # noqa: BLE001
        parse_ok = False
        error = str(exc)
        raw = {
            "text": f"生成失败：{exc}",
            "card": {"card_type": "training_draft", "title": "草稿", "items": []},
        }
    preview = str(raw.get("text") or "")[:80]
    return {
        "raw": raw,
        "parse_ok": parse_ok,
        "error": error,
        **_step(
            "draft_plan",
            started,
            parse_ok=parse_ok,
            error=error,
            text=preview,
            tools=[t.get("tool") for t in tool_trace],
        ),
    }


_MEMORY_CUES = ("上次", "上一次", "我的记录", "体重", "涨了", "最近重量")
_NUTRITION_TEXT = "营养师还没上线。饮食相关以后会单独接；现在先问训练计划或动作问题。"


def _is_memory_question(text: str) -> bool:
    return any(cue in (text or "") for cue in _MEMORY_CUES)


def _answer_from_records(hits: list[dict[str, Any]]) -> str:
    """有记录就用记录里的数。没有记录才说没有。"""
    parts: list[str] = []
    for hit in hits:
        weight = hit.get("last_weight")
        if weight is None or weight == "":
            continue
        name = str(hit.get("name") or "这个动作")
        if isinstance(weight, (int, float)):
            weight_text = f"{weight:g}"
        else:
            weight_text = str(weight)
        reps = hit.get("last_reps")
        if reps:
            parts.append(f"你上次{name}是{weight_text}公斤，{reps}次。")
        else:
            parts.append(f"你上次{name}是{weight_text}公斤。")
    if not parts:
        return "档案里没有可核对的历史重量记录。"
    return "".join(parts)


async def ground_knowledge_node(state: ChatState) -> dict[str, Any]:
    """chat 路由上的知识库 / 反问 / 搜索判定。排课和营养不进这里。"""
    started = time.perf_counter()
    from app.brain.knowledge import Grounding, ground_question

    intent = _intent(state.get("intent") or {})
    if intent.params.get("adopt_hint"):
        decided = Grounding(branch="adopt", reason="not_queried", queried=False, hit=False)
    elif intent.params.get("topic") == "chitchat":
        # 闲聊不查动作库、不调搜索，直接走 LLM 接话
        decided = Grounding(branch="llm", reason="chitchat", queried=False, hit=False)
    elif _is_memory_question(state.get("user_text") or ""):
        decided = Grounding(branch="memory", reason="not_queried", queried=False, hit=False)
    else:
        decided = ground_question(state.get("user_text") or "", state.get("history"))
        mode = state.get("search_mode") or "off"
        if decided.branch == "search" and mode != "off":
            decided.search_called = True
            if mode == "fixture":
                decided.search_results = list(state.get("search_fixture") or [])
    payload = decided.as_dict()
    return {
        "grounding": payload,
        **_step(
            "ground_knowledge",
            started,
            branch=payload["branch"],
            reason=payload["kb"]["reason"],
            search_called=payload["search"]["called"],
        ),
    }


async def eval_shortcut_node(state: ChatState) -> dict[str, Any]:
    """评测里的排课 / 反问 / 营养不跑工具循环，只回路由说明。"""
    started = time.perf_counter()
    route = state.get("route") or "plan"
    if route == "nutrition":
        text = _NUTRITION_TEXT
    elif route == "clarify":
        text = "这句先确认一下训练安排。"
    else:
        text = "这句走排课。"
    grounding = {
        "branch": route,
        "model_called": False,
        "suggestions": [],
        "citations": [],
        "answer": text,
        "kb": {
            "queried": False,
            "hit": False,
            "top_score": 0.0,
            "margin": 0.0,
            "reason": "not_queried",
            "hits": [],
            "near_miss": [],
        },
        "search": {"called": False, "query": None, "results": []},
    }
    return {
        "blocks": [{"kind": "text", "text": text}],
        "suggestions": [],
        "grounding": grounding,
        "parse_ok": True,
        **_step("eval_shortcut", started, route=route),
    }


_ADOPT_HINT_WITH_DRAFT = "要开始练，点上面卡片上的「采纳 · 进入今日执行」。"
_ADOPT_HINT_NO_DRAFT = "还没有排好的训练。先说今天练什么，排好之后点卡片上的「采纳」。"


def _finish_reply(
    started: float,
    grounding: dict[str, Any],
    text: str,
    *,
    suggestions: list[dict[str, str]] | None = None,
    model_called: bool = False,
    prompt: str = "",
    raw: dict[str, Any] | None = None,
    parse_ok: bool = True,
    error: str | None = None,
    profile_text: str = "",
    node: str = "chat_reply",
) -> dict[str, Any]:
    updated = dict(grounding)
    updated["model_called"] = model_called
    updated["answer"] = text
    sug = suggestions if suggestions is not None else list(grounding.get("suggestions") or [])
    updated["suggestions"] = sug
    return {
        "grounding": updated,
        "suggestions": sug,
        "memory": {"profile_summary": profile_text, "derived": [], "logs": [], "token_estimate": 0},
        "prompt_user": prompt,
        "raw": raw or {"text": text},
        "parse_ok": parse_ok,
        "error": error,
        "blocks": [{"kind": "text", "text": text}],
        **_step(node, started, parse_ok=parse_ok, text=text[:80], branch=grounding.get("branch")),
    }


async def chat_reply_node(state: ChatState) -> dict[str, Any]:
    started = time.perf_counter()
    intent = _intent(state.get("intent") or {})
    grounding = dict(state.get("grounding") or {})
    branch = grounding.get("branch")
    question = state.get("user_text") or ""

    if branch == "adopt" or intent.params.get("adopt_hint"):
        has_draft = bool(state.get("draft_items"))
        text = _ADOPT_HINT_WITH_DRAFT if has_draft else _ADOPT_HINT_NO_DRAFT
        grounding["branch"] = "adopt"
        return _finish_reply(started, grounding, text)

    if branch == "memory":
        profile = get_current_profile(_session())
        if "体重" in question and "上次" not in question and profile is not None:
            if profile.weight_kg is None:
                text = "档案里还没填体重，记一笔后再问我。"
            else:
                text = f"你的体重是{profile.weight_kg:g}公斤。"
            return _finish_reply(started, grounding, text, profile_text=build_profile_summary(profile))
        from app.brain.knowledge_reply import collect_training_stats

        _stats_text, stats = collect_training_stats(
            _session(),
            intent,
            question,
            stats_fixture=state.get("stats_fixture") or None,
        )
        text = _answer_from_records(stats.get("hits") or [])
        reply = _finish_reply(started, grounding, text, profile_text=build_profile_summary(profile))
        reply["stats"] = stats
        return reply

    return _finish_reply(started, grounding, "可以说具体一点。")


async def nutrition_reply_node(state: ChatState) -> dict[str, Any]:
    started = time.perf_counter()
    text = _NUTRITION_TEXT
    blocks = [{"kind": "text", "text": text}]
    return {
        "blocks": blocks,
        "suggestions": [],
        **_step("nutrition_reply", started, text=text),
    }


async def validate_node(state: ChatState) -> dict[str, Any]:
    started = time.perf_counter()
    intent = _intent(state["intent"])
    blocks = validate_and_build_blocks(state.get("raw") or {}, state.get("injuries") or [])
    titled = draft_title_for_intent(intent)
    # 改草稿换掉不可用动作时，保留模型沿用的原标题，不要用排除项当标题
    if titled and not intent.params.get("exclude_exercises"):
        blocks = [
            block.model_copy(update={"title": titled}) if getattr(block, "kind", None) == "card" else block
            for block in blocks
        ]
    blocks = [_normalize_card_title(block) for block in blocks]
    blocks = [_select_all_items(block) for block in blocks]
    # 仅「只要点名这几个」时裁草稿；普通侧重/部位课交给 LLM 从候选库选，避免误匹配裁空
    if (
        intent.params.get("focus_exercises")
        and intent.params.get("exclusive_focus")
        and not intent.params.get("exclude_exercises")
    ):
        blocks = _trim_to_request(blocks, intent)
    dumped = [block.model_dump(mode="json") for block in blocks]
    titles = [b.get("title") for b in dumped if b.get("kind") == "card"]
    return {
        "blocks": dumped,
        **_step("validate", started, titles=titles, blocks=len(dumped)),
    }


def _after_ground(state: ChatState) -> Literal["chat_reply", "knowledge_reply"]:
    branch = (state.get("grounding") or {}).get("branch")
    if branch in ("adopt", "memory"):
        return "chat_reply"
    return "knowledge_reply"


def _route(state: ChatState) -> Literal["clarify", "plan", "chat", "nutrition", "eval_shortcut", "intent_only"]:
    if state.get("intent_only"):
        return "intent_only"
    route = state.get("route") or "plan"
    if state.get("eval_mode") and route in ("plan", "clarify", "nutrition"):
        return "eval_shortcut"
    return route


async def intent_only_node(state: ChatState) -> dict[str, Any]:
    """意图评测只取 topic，不检索、不写回答。"""
    started = time.perf_counter()
    return {
        "blocks": [],
        "suggestions": [],
        **_step("intent_only", started, route=state.get("route")),
    }


def _draft_views(items: list[dict[str, Any]]) -> list[Any]:
    from types import SimpleNamespace

    views = []
    for item in items:
        meta = item.get("meta") or {}
        views.append(
            SimpleNamespace(
                title=item.get("title") or "",
                selected=item.get("selected", True),
                meta=meta,
            )
        )
    return views


def build_chat_graph():
    graph = StateGraph(ChatState)
    graph.add_node("rewrite_intent", rewrite_intent_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("assemble_memory", assemble_memory_node)
    graph.add_node("draft_plan", draft_plan_node)
    graph.add_node("validate", validate_node)
    graph.add_node("chat_reply", chat_reply_node)
    graph.add_node("knowledge_reply", knowledge_reply_node)
    graph.add_node("ground_knowledge", ground_knowledge_node)
    graph.add_node("eval_shortcut", eval_shortcut_node)
    graph.add_node("intent_only", intent_only_node)
    graph.add_node("nutrition_reply", nutrition_reply_node)
    graph.set_entry_point("rewrite_intent")
    graph.add_conditional_edges(
        "rewrite_intent",
        _route,
        {
            "clarify": "clarify",
            "plan": "assemble_memory",
            "chat": "ground_knowledge",
            "nutrition": "nutrition_reply",
            "eval_shortcut": "eval_shortcut",
            "intent_only": "intent_only",
        },
    )
    graph.add_conditional_edges(
        "ground_knowledge",
        _after_ground,
        {"chat_reply": "chat_reply", "knowledge_reply": "knowledge_reply"},
    )
    graph.add_edge("eval_shortcut", END)
    graph.add_edge("intent_only", END)
    graph.add_edge("clarify", END)
    graph.add_edge("chat_reply", END)
    graph.add_edge("knowledge_reply", END)
    graph.add_edge("nutrition_reply", END)
    graph.add_edge("assemble_memory", "draft_plan")
    graph.add_edge("draft_plan", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


def get_chat_graph():
    """Build lazily so tests/reloads pick up node changes."""
    return build_chat_graph()


chat_graph = get_chat_graph()


def enable_langsmith() -> None:
    """Turn on LangSmith only when a key is configured. The local trace is always kept."""
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return
    project = (settings.langsmith_project or "Gym_coach").strip().strip('"')
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.strip().strip('"')
    os.environ["LANGSMITH_PROJECT"] = project
    # langsmith caches env lookups; a key set at request time would otherwise stay invisible
    from langsmith.utils import get_env_var

    get_env_var.cache_clear()


async def invoke_chat_graph(
    session: Session,
    *,
    user_text: str,
    draft_title: str | None,
    draft_items: list[Any],
    history: list[Any] | None = None,
    eval_mode: bool = False,
    intent_only: bool = False,
    search_mode: str = "off",
    search_fixture: list[dict[str, Any]] | None = None,
    stats_fixture: list[dict[str, Any]] | None = None,
) -> ChatState:
    enable_langsmith()
    token = _db.set(session)
    try:
        items = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
            for item in draft_items
        ]
        turns = [
            turn.model_dump(mode="json") if hasattr(turn, "model_dump") else dict(turn)
            for turn in (history or [])
        ]
        result = await get_chat_graph().ainvoke(
            {
                "user_text": user_text,
                "history": turns,
                "draft_title": draft_title,
                "draft_items": items,
                "steps": [],
                "eval_mode": eval_mode,
                "intent_only": intent_only,
                "search_mode": search_mode,
                "search_fixture": list(search_fixture or []),
                "stats_fixture": list(stats_fixture or []),
            },
            config={
                "run_name": "gym_coach_chat",
                "tags": ["gym-coach"],
                "metadata": {
                    "user_text": user_text[:180],
                    "history_turns": len(turns),
                },
            },
        )
        return result
    finally:
        _db.reset(token)
