"""Plan-path tools: model decides what to fetch (retrieve / stats / recent), then submits draft."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, select

from app.brain.memory import Intent, _format_stat_line, _stats_match_modalities, session_modalities
from app.exercises_catalog import (
    EXERCISE_BY_NAME,
    format_candidates_block,
    retrieve_candidates,
    roles_of,
)
from app.models import ExerciseStats, Profile, TrainingSetLog
from app.taxonomy import canonicalize_exercise

# OpenAI-compatible tool schemas
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_exercises",
            "description": (
                "从动作库检索本堂候选动作。按部位/课型/器械/排除筛选；"
                "同档会打乱，便于定制与随机。排课前应至少调用一次。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "muscles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "部位，如 [\"背\"]；全身课可省略",
                    },
                    "modalities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "课型：抗阻/有氧/HIIT/灵活性",
                    },
                    "equipment": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "器械限制：自重/自由重量/器械/绳索",
                    },
                    "exclude": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "不要排的动作名或简称",
                    },
                    "focus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户点名的动作，检索时提高权重",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数，默认 24，最大 40",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_stats",
            "description": (
                "查询与本堂相关的历史重量/趋势。必须按本堂部位或课型过滤，"
                "不要拉全站无关肌群。定负荷前调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "muscles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "只要这些部位角色的动作统计",
                    },
                    "modalities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "课型过滤，默认跟本堂意图",
                    },
                    "limit": {"type": "integer", "description": "最多几条，默认 6"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_sets",
            "description": "最近几组完成记录，按本堂部位/课型过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "muscles": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "modalities": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "limit": {"type": "integer", "description": "默认 5"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_training_draft",
            "description": "提交最终训练草稿。信息够了就调用这个结束，不要空转。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "给学员的 1~2 句说明"},
                    "title": {"type": "string", "description": "卡片标题"},
                    "items": {
                        "type": "array",
                        "description": "动作列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "subtitle": {"type": "string"},
                                "selected": {"type": "boolean"},
                                "meta": {
                                    "type": "object",
                                    "properties": {
                                        "sets": {"type": "integer"},
                                        "reps": {"type": "string"},
                                        "weight": {"type": "number"},
                                        "muscle": {"type": "string"},
                                    },
                                    "required": ["sets", "reps", "muscle"],
                                },
                            },
                            "required": ["title", "meta"],
                        },
                    },
                },
                "required": ["text", "title", "items"],
            },
        },
    },
]


@dataclass
class ToolContext:
    session: Session
    profile: Profile | None
    intent: Intent
    injuries: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)


def _stats_match_muscles(name: str, want: list[str]) -> bool:
    if not want:
        return True
    roles = roles_of(name) or []
    return any(m in roles for m in want)


def _default_muscles(ctx: ToolContext, args: dict[str, Any]) -> list[str]:
    raw = args.get("muscles")
    if isinstance(raw, list) and raw:
        return [str(m) for m in raw if m and str(m) != "全身"]
    return [m for m in (ctx.intent.muscles or []) if m != "全身"]


def _default_modalities(ctx: ToolContext, args: dict[str, Any]) -> list[str]:
    raw = args.get("modalities")
    if isinstance(raw, list) and raw:
        return [str(m) for m in raw if m]
    mods = session_modalities(ctx.intent)
    return mods or ["抗阻"]


def tool_retrieve_exercises(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    muscles = _default_muscles(ctx, args)
    modalities = _default_modalities(ctx, args)
    equipment = args.get("equipment")
    if not isinstance(equipment, list):
        equipment = list(ctx.intent.params.get("equipment") or []) or None
    exclude = list(args.get("exclude") or []) + list(ctx.avoid)
    intent_exclude = list(ctx.intent.params.get("exclude_exercises") or [])
    exclude = list(dict.fromkeys([*exclude, *intent_exclude]))
    focus = list(args.get("focus") or []) or list(ctx.intent.params.get("focus_exercises") or [])
    limit = int(args.get("limit") or 24)
    limit = max(4, min(limit, 40))

    boost = []
    for s in ctx.session.exec(select(ExerciseStats).limit(60)).all():
        if muscles and not _stats_match_muscles(s.exercise_name, muscles):
            continue
        if not _stats_match_modalities(s.exercise_name, modalities):
            continue
        boost.append(s.exercise_name)
        if len(boost) >= 20:
            break

    candidates = retrieve_candidates(
        muscles=muscles or None,
        modalities=modalities or None,
        equipment=equipment,
        injuries=ctx.injuries,
        exclude=exclude,
        focus=focus,
        boost_names=boost,
        limit=limit,
    )
    have = {c["name"] for c in candidates}
    for name in focus:
        if not name or name in have:
            continue
        detail = EXERCISE_BY_NAME.get(canonicalize_exercise(name))
        if detail:
            candidates.insert(0, detail)
            have.add(detail["name"])

    block = format_candidates_block(candidates)
    return {
        "count": len(candidates),
        "block": block,
        "names": [c["name"] for c in candidates],
    }


def tool_get_related_stats(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    muscles = _default_muscles(ctx, args)
    modalities = _default_modalities(ctx, args)
    limit = max(1, min(int(args.get("limit") or 6), 12))
    lines: list[str] = []
    hits: list[dict[str, Any]] = []
    for s in ctx.session.exec(select(ExerciseStats).limit(80)).all():
        if not _stats_match_modalities(s.exercise_name, modalities):
            continue
        if muscles and not _stats_match_muscles(s.exercise_name, muscles):
            continue
        lines.append(_format_stat_line(s))
        hits.append(
            {
                "name": s.exercise_name,
                "last_weight": s.last_weight,
                "last_reps": s.last_reps,
                "trend": s.trend,
            }
        )
        if len(lines) >= limit:
            break
    return {
        "count": len(lines),
        "lines": lines,
        "hits": hits,
        "text": "\n".join(lines) if lines else "（本堂相关暂无历史重量）",
    }


def tool_get_recent_sets(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    muscles = _default_muscles(ctx, args)
    modalities = _default_modalities(ctx, args)
    limit = max(1, min(int(args.get("limit") or 5), 12))
    lines: list[str] = []
    if muscles:
        q = (
            select(TrainingSetLog)
            .where(TrainingSetLog.muscle.in_(muscles))  # type: ignore[attr-defined]
            .order_by(TrainingSetLog.id.desc())
            .limit(40)
        )
    else:
        q = select(TrainingSetLog).order_by(TrainingSetLog.id.desc()).limit(40)
    for r in ctx.session.exec(q).all():
        if muscles and r.muscle and r.muscle not in muscles:
            continue
        if not muscles and not _stats_match_modalities(r.exercise_name, modalities):
            continue
        feel = f" feel={r.feeling}" if r.feeling else ""
        if r.target_weight is not None:
            lines.append(
                f"{r.exercise_name} set#{r.set_index} "
                f"计划={r.target_weight}kg×{r.target_reps or '-'} "
                f"实际={r.actual_weight or r.target_weight}kg×{r.actual_reps or '-'} "
                f"done={r.completed}{feel}"
            )
        else:
            lines.append(
                f"{r.exercise_name} set#{r.set_index} "
                f"计划={r.target_reps or '-'} "
                f"实际={r.actual_reps or '-'} "
                f"done={r.completed}{feel}"
            )
        if len(lines) >= limit:
            break
    return {"count": len(lines), "lines": lines, "text": "\n".join(lines) if lines else "（本堂相关暂无组记录）"}


def tool_submit_training_draft(_ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    items = args.get("items") or []
    if not isinstance(items, list):
        items = []
    normalized = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        meta = dict(it.get("meta") or {})
        normalized.append(
            {
                "id": it.get("id") or f"c{i+1}",
                "title": it.get("title") or f"动作{i+1}",
                "subtitle": it.get("subtitle") or "",
                "selected": it.get("selected", True),
                "meta": meta,
            }
        )
    return {
        "ok": True,
        "plan": {
            "text": str(args.get("text") or "按你的情况排好了。"),
            "card": {
                "card_type": "training_draft",
                "title": str(args.get("title") or "训练"),
                "items": normalized,
            },
        },
    }


_HANDLERS = {
    "retrieve_exercises": tool_retrieve_exercises,
    "get_related_stats": tool_get_related_stats,
    "get_recent_sets": tool_get_recent_sets,
    "submit_training_draft": tool_submit_training_draft,
}


def execute_tool(name: str, args: dict[str, Any] | None, ctx: ToolContext) -> dict[str, Any]:
    handler = _HANDLERS.get(name)
    payload = args if isinstance(args, dict) else {}
    if handler is None:
        result: dict[str, Any] = {"error": f"unknown tool: {name}"}
    else:
        result = handler(ctx, payload)
    ctx.tool_trace.append({"tool": name, "args": payload, "result_keys": list(result.keys())})
    return result


def build_tool_context(session: Session, intent: Intent, profile: Profile | None) -> ToolContext:
    injuries = list(profile.injuries) if profile and profile.injuries else []
    avoid = list(getattr(profile, "avoid_exercises", None) or []) if profile else []
    return ToolContext(
        session=session,
        profile=profile,
        intent=intent,
        injuries=injuries,
        avoid=avoid,
    )
