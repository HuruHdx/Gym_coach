"""Plan agent: model loops over tools then submits a training draft."""

from __future__ import annotations

import json
from typing import Any

from app.brain.llm import TEMPERATURE_PLAN, LLMClient, MockLLM, _extract_json
from app.brain.tools import TOOL_SCHEMAS, ToolContext, execute_tool


def _run_traced_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """执行工具，并在开了 LangSmith 时记成子 run，方便在 trace 里看到调用。"""
    try:
        from langsmith.run_helpers import trace as ls_trace
    except Exception:  # noqa: BLE001
        return execute_tool(name, args, ctx)

    with ls_trace(name=name, run_type="tool", inputs=args or {}) as run:
        result = execute_tool(name, args, ctx)
        preview = result.get("text") or result.get("block") or ""
        if run is not None:
            run.outputs = {"preview": str(preview)[:400], "keys": list(result.keys())}
        return result


PLAN_TOOL_SYSTEM = """【PLAN_TOOLS】
【角色】
你是 Gym Coach 的训练计划编排教练，通过工具按需取数，再提交草稿。

【工作方式】
1) 先看「结构化意图」与档案，自己决定调哪些工具（可多轮）。
2) 排课前至少调用 retrieve_exercises 拿到候选；定重量前调用 get_related_stats（按本堂部位，不要查无关肌群）。
3) 信息够了就调用 submit_training_draft 结束；不要空转，不要用纯文本代替提交。

【约束】
1) 对学员用「你」，不要把档案字段当称呼。
2) 动作名优先用 retrieve 返回的标准中文名；meta 必含 sets、reps、muscle。
3) 抗阻写 weight（kg），自重/有氧/HIIT/灵活性不写 weight。
4) 有标题=xxx 时 card.title 原样用；改稿只替换不可用项，保留其余与原标题。
5) get_related_stats / get_recent_sets 的 muscles 必须跟本堂部位一致（如练背就传 ["背"]）。
"""


def _supports_tool_loop(llm: LLMClient) -> bool:
    if isinstance(llm, MockLLM):
        return False
    meth = getattr(type(llm), "chat_turn", None)
    return callable(meth) and meth is not LLMClient.chat_turn


async def draft_plan_with_tools(
    llm: LLMClient,
    user_prompt: str,
    ctx: ToolContext,
    *,
    max_rounds: int = 6,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Returns (plan_json, tool_trace)."""
    if not _supports_tool_loop(llm):
        return await _prefetch_then_json(llm, user_prompt, ctx)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": PLAN_TOOL_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    for _ in range(max_rounds):
        turn = await llm.chat_turn(messages, tools=TOOL_SCHEMAS, temperature=TEMPERATURE_PLAN)
        tool_calls = turn.get("tool_calls") or []
        content = turn.get("content") or ""

        if not tool_calls:
            # 模型直接吐 JSON 时兜底
            if content.strip():
                try:
                    raw = _extract_json(content)
                    if isinstance(raw.get("card"), dict):
                        return raw, ctx.tool_trace
                except ValueError:
                    pass
            messages.append({"role": "assistant", "content": content or "请调用 submit_training_draft 提交计划。"})
            messages.append(
                {
                    "role": "user",
                    "content": "请调用 submit_training_draft 提交最终草稿，不要只回复文字。",
                }
            )
            continue

        messages.append(
            {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc.get("id") or f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
                        },
                    }
                    for i, tc in enumerate(tool_calls)
                ],
            }
        )

        submitted: dict[str, Any] | None = None
        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = _run_traced_tool(name, args, ctx)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or "call",
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
            if name == "submit_training_draft" and result.get("ok"):
                submitted = result["plan"]

        if submitted is not None:
            return submitted, ctx.tool_trace

    # 超时兜底：强制检索一次再走旧 complete_json
    retrieve = _run_traced_tool(
        "retrieve_exercises",
        {"muscles": list(ctx.intent.muscles or []), "limit": 20},
        ctx,
    )
    stats = _run_traced_tool(
        "get_related_stats",
        {"muscles": list(ctx.intent.muscles or []), "limit": 6},
        ctx,
    )
    fallback_user = (
        f"{user_prompt}\n\n"
        f"{retrieve.get('block') or ''}\n"
        f"相关训练：\n{stats.get('text') or ''}\n"
    )
    raw = await llm.complete_json(
        "【PLAN】只输出 training_draft JSON：{\"text\":\"...\",\"card\":{...}}",
        fallback_user,
        temperature=TEMPERATURE_PLAN,
    )
    return raw, ctx.tool_trace


async def _prefetch_then_json(
    llm: LLMClient,
    user_prompt: str,
    ctx: ToolContext,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """无 tool-calling 时：按本堂意图拉候选+相关统计，再 complete_json。"""
    muscles = [m for m in (ctx.intent.muscles or []) if m != "全身"]
    retrieve = _run_traced_tool("retrieve_exercises", {"muscles": muscles, "limit": 20}, ctx)
    stats = _run_traced_tool("get_related_stats", {"muscles": muscles, "limit": 6}, ctx)
    recent = _run_traced_tool("get_recent_sets", {"muscles": muscles, "limit": 5}, ctx)
    enriched = (
        f"{user_prompt}\n\n"
        f"{retrieve.get('block') or ''}\n"
        f"相关训练：\n{stats.get('text') or ''}\n"
        f"最近组记录：\n{recent.get('text') or ''}\n"
    )
    from app.brain.pipeline import SYSTEM_PROMPT

    raw = await llm.complete_json(SYSTEM_PROMPT, enriched, temperature=TEMPERATURE_PLAN)
    execute_tool(
        "submit_training_draft",
        {
            "text": raw.get("text") or "",
            "title": (raw.get("card") or {}).get("title") or "训练",
            "items": (raw.get("card") or {}).get("items") or [],
        },
        ctx,
    )
    return raw, ctx.tool_trace
