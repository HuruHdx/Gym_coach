"""AI Ops：未命中动作池 + 差评收件箱。"""

from __future__ import annotations

import importlib.util
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.exercises_catalog import reload_all
from app.models import (
    AiOpsMissState,
    DebugTrace,
    Exercise,
    ExerciseAlias,
    FeedbackEvent,
    utcnow,
)

MissStatus = Literal["pending", "bound", "created_sku", "ignored"]
ResolveStatus = Literal["created_sku", "ignored"]


def _norm_query(text: str) -> str:
    cleaned = re.sub(r"\s+", "", (text or "").strip().lower())
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "", cleaned)
    return cleaned[:120]


def _kb_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    grounding = payload.get("grounding") if isinstance(payload.get("grounding"), dict) else {}
    kb = grounding.get("kb") if isinstance(grounding.get("kb"), dict) else {}
    return kb


def _is_kb_miss(payload: dict[str, Any]) -> bool:
    grounding = payload.get("grounding") if isinstance(payload.get("grounding"), dict) else {}
    kb = _kb_from_payload(payload)
    branch = str(grounding.get("branch") or "")
    reason = str(kb.get("reason") or "")
    if kb.get("queried") is True and kb.get("hit") is False:
        return True
    if reason in {"miss", "below_miss"}:
        return True
    if branch in {"search", "ask"} and kb.get("hit") is False:
        return True
    return False


def _extract_query_surface(trace: DebugTrace) -> str:
    payload = trace.payload or {}
    grounding = payload.get("grounding") if isinstance(payload.get("grounding"), dict) else {}
    search = grounding.get("search") if isinstance(grounding.get("search"), dict) else {}
    for candidate in (
        search.get("query"),
        payload.get("user_text"),
        trace.user_text,
    ):
        text = str(candidate or "").strip()
        if text:
            return text[:120]
    return (trace.user_text or "").strip()[:120]


def _near_miss_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    kb = _kb_from_payload(payload)
    raw = kb.get("near_miss") if isinstance(kb.get("near_miss"), list) else []
    out: list[dict[str, Any]] = []
    for item in raw[:5]:
        if isinstance(item, dict):
            out.append(
                {
                    "exercise_id": item.get("id") or item.get("exercise_id"),
                    "name_zh": item.get("name_zh") or item.get("name") or "",
                    "score": item.get("score"),
                }
            )
        elif isinstance(item, str) and item.strip():
            out.append({"exercise_id": None, "name_zh": item.strip(), "score": None})
    return out


def _state_map(session: Session) -> dict[str, AiOpsMissState]:
    rows = session.exec(select(AiOpsMissState)).all()
    return {row.norm_query: row for row in rows if row.norm_query}


def list_missed_queries(
    session: Session,
    *,
    status: str = "pending",
    limit_traces: int = 300,
) -> list[dict[str, Any]]:
    """聚合最近 DebugTrace 里的 KB 未命中。"""
    traces = list(
        session.exec(select(DebugTrace).order_by(col(DebugTrace.id).desc()).limit(max(50, min(limit_traces, 1000)))).all()
    )
    states = _state_map(session)
    buckets: dict[str, dict[str, Any]] = {}

    for trace in traces:
        payload = trace.payload if isinstance(trace.payload, dict) else {}
        if not _is_kb_miss(payload):
            continue
        surface = _extract_query_surface(trace)
        key = _norm_query(surface)
        if not key:
            continue
        state = states.get(key)
        state_status = (state.status if state else "pending") or "pending"
        if status == "pending" and state_status != "pending":
            continue
        if status == "done" and state_status == "pending":
            continue
        if status not in {"", "all", "pending", "done"} and state_status != status:
            continue

        bucket = buckets.get(key)
        created = trace.created_at.isoformat() if isinstance(trace.created_at, datetime) else None
        if bucket is None:
            buckets[key] = {
                "norm_query": key,
                "display_query": surface,
                "count": 1,
                "last_at": created,
                "examples": [trace.user_text][:1],
                "near_miss": _near_miss_list(payload),
                "trace_ids": [trace.id],
                "status": state_status,
                "bound_exercise_id": state.bound_exercise_id if state else None,
                "note": state.note if state else None,
            }
            continue
        bucket["count"] = int(bucket["count"]) + 1
        if created and (not bucket.get("last_at") or created > str(bucket["last_at"])):
            bucket["last_at"] = created
            bucket["near_miss"] = _near_miss_list(payload) or bucket["near_miss"]
        examples = list(bucket.get("examples") or [])
        if trace.user_text and trace.user_text not in examples and len(examples) < 3:
            examples.append(trace.user_text)
            bucket["examples"] = examples
        ids = list(bucket.get("trace_ids") or [])
        if trace.id not in ids and len(ids) < 20:
            ids.append(trace.id)
            bucket["trace_ids"] = ids

    items = sorted(
        buckets.values(),
        key=lambda row: (str(row.get("last_at") or ""), int(row.get("count") or 0)),
        reverse=True,
    )
    return items


def _catalog_candidates(session: Session, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    rows = list(
        session.exec(
            select(Exercise)
            .where(
                (col(Exercise.name_zh).ilike(like))
                | (col(Exercise.name_en).ilike(like))
                | (col(Exercise.id) == q)
            )
            .limit(limit)
        ).all()
    )
    if len(rows) < limit:
        alias_ids = list(
            session.exec(
                select(ExerciseAlias.exercise_id).where(
                    ExerciseAlias.status == "published",
                    col(ExerciseAlias.alias).ilike(like),
                ).limit(limit)
            ).all()
        )
        have = {r.id for r in rows}
        for eid in alias_ids:
            if eid in have:
                continue
            ex = session.get(Exercise, eid)
            if ex is not None:
                rows.append(ex)
                have.add(eid)
            if len(rows) >= limit:
                break
    # JSON catalog fallback when DB exercises empty (local seed may lag)
    if not rows:
        try:
            from app.exercises_catalog import EXERCISES_DATABASE, ensure_loaded

            ensure_loaded()
            needle = q.lower()
            for detail in EXERCISES_DATABASE:
                name = str(detail.get("name") or "")
                blob = f"{name} {detail.get('id') or ''}".lower()
                if needle in blob or needle in name:
                    rows.append(
                        type("Tmp", (), {
                            "id": detail.get("id"),
                            "name_zh": name,
                        })()
                    )
                if len(rows) >= limit:
                    break
        except Exception:
            pass
    out: list[dict[str, Any]] = []
    for row in rows[:limit]:
        out.append(
            {
                "exercise_id": getattr(row, "id", None),
                "name_zh": getattr(row, "name_zh", None) or getattr(row, "name", "") or "",
                "confidence": 0.55,
            }
        )
    return out


def _heuristic_miss_diagnosis(query: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if candidates:
        top = candidates[0]
        return {
            "verdict": "has_match",
            "reason": f"库内已有相近动作「{top.get('name_zh')}」，更像口语别名没绑上。",
            "suggested_candidates": candidates[:3],
            "suggested_alias": query.strip()[:40] or None,
        }
    return {
        "verdict": "missing_exercise",
        "reason": "候选库里没有明显同名动作，可能需要新建 SKU，或属于非动作闲聊。",
        "suggested_candidates": [],
        "suggested_alias": query.strip()[:40] or None,
    }


async def diagnose_missed_query(
    session: Session,
    *,
    norm_query: str,
    display_query: str | None = None,
    examples: list[str] | None = None,
) -> dict[str, Any]:
    query = (display_query or norm_query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="缺少未命中词")
    candidates = _catalog_candidates(session, query, limit=10)
    example_lines = "\n".join(f"- {x}" for x in (examples or [])[:3]) or "- （无）"
    system = (
        "【AI_OPS_MISS_DIAGNOSE】你是健身动作库运营助手。"
        "判断用户口语词在动作库里有没有对应 SKU。只返回 JSON："
        '{"verdict":"has_match|missing_exercise|non_exercise","reason":string,'
        '"suggested_candidates":[{"exercise_id":string,"name_zh":string,"confidence":number}],'
        '"suggested_alias":string|null}'
        "规则：has_match=库里有只是没认出；missing_exercise=真缺动作；non_exercise=肌群/闲聊无需建动作。"
    )
    user = (
        f"未命中词：{query}\n"
        f"示例原句：\n{example_lines}\n"
        f"库内候选 Top：\n{candidates}\n"
    )
    raw: dict[str, Any] = {}
    try:
        from app.brain.llm import TEMPERATURE_STRUCTURED, get_llm

        llm = get_llm()
        raw = await llm.complete_json(system, user, temperature=TEMPERATURE_STRUCTURED)
    except Exception:
        raw = {}

    if not isinstance(raw, dict) or raw.get("verdict") not in {
        "has_match",
        "missing_exercise",
        "non_exercise",
    }:
        return _heuristic_miss_diagnosis(query, candidates)

    suggested = raw.get("suggested_candidates")
    if not isinstance(suggested, list) or not suggested:
        suggested = candidates[:3]
    cleaned = []
    for item in suggested[:3]:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "exercise_id": item.get("exercise_id") or item.get("id"),
                "name_zh": item.get("name_zh") or item.get("name") or "",
                "confidence": float(item.get("confidence") or 0.5),
            }
        )
    alias = raw.get("suggested_alias")
    return {
        "verdict": raw.get("verdict"),
        "reason": str(raw.get("reason") or "").strip() or "（无说明）",
        "suggested_candidates": cleaned,
        "suggested_alias": str(alias).strip() if isinstance(alias, str) and alias.strip() else query[:40],
    }


def _upsert_miss_state(
    session: Session,
    *,
    norm_query: str,
    status: MissStatus,
    bound_exercise_id: str | None = None,
    note: str | None = None,
) -> AiOpsMissState:
    key = _norm_query(norm_query)
    if not key:
        raise HTTPException(status_code=400, detail="无效的未命中词")
    row = session.exec(select(AiOpsMissState).where(AiOpsMissState.norm_query == key)).first()
    if row is None:
        row = AiOpsMissState(norm_query=key)
    row.status = status
    row.bound_exercise_id = bound_exercise_id
    row.note = note
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def ensure_exercise_alias(
    session: Session,
    *,
    exercise_id: str,
    alias: str,
) -> dict[str, Any]:
    """写入 ExerciseAlias 并热重载问答索引（工坊口播词 / 未命中池共用）。"""
    eid = (exercise_id or "").strip()
    surface = (alias or "").strip()
    if not eid:
        raise HTTPException(status_code=400, detail="缺少 exercise_id")
    if not surface:
        raise HTTPException(status_code=400, detail="缺少别名")

    ex = session.get(Exercise, eid)
    catalog_name = None
    if ex is None:
        try:
            from app.exercises_catalog import EXERCISES_DATABASE, ensure_loaded

            ensure_loaded()
            hit = next((d for d in EXERCISES_DATABASE if str(d.get("id")) == eid), None)
            if hit is None:
                raise HTTPException(status_code=404, detail="动作不存在")
            catalog_name = str(hit.get("name") or "")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail="动作不存在") from exc

    # 口播词与正式名相同则无需别名
    official = ((ex.name_zh if ex else catalog_name) or "").strip()
    if official and _norm_query(official) == _norm_query(surface):
        return {
            "ok": True,
            "skipped": True,
            "bound_exercise_id": eid,
            "alias": surface,
            "exercise_name_zh": official,
        }

    existing = session.exec(
        select(ExerciseAlias).where(
            ExerciseAlias.exercise_id == eid,
            ExerciseAlias.alias == surface,
        )
    ).first()
    created = False
    if existing is None:
        session.add(ExerciseAlias(exercise_id=eid, alias=surface, status="published"))
        session.commit()
        created = True
    elif existing.status != "published":
        existing.status = "published"
        session.add(existing)
        session.commit()
        created = True

    from app.brain import knowledge as knowledge_mod

    knowledge_mod.register_alias(eid, surface)
    reload_all()
    knowledge_mod.register_alias(eid, surface)

    return {
        "ok": True,
        "skipped": False,
        "created": created,
        "bound_exercise_id": eid,
        "alias": surface,
        "exercise_name_zh": official,
    }


def bind_miss_to_alias(
    session: Session,
    *,
    norm_query: str,
    exercise_id: str,
    alias: str | None = None,
) -> dict[str, Any]:
    surface = (alias or norm_query or "").strip()
    result = ensure_exercise_alias(session, exercise_id=exercise_id, alias=surface)
    state = _upsert_miss_state(
        session,
        norm_query=norm_query,
        status="bound",
        bound_exercise_id=result["bound_exercise_id"],
        note=f"bound alias={result['alias']}",
    )
    return {
        "ok": True,
        "norm_query": state.norm_query,
        "status": state.status,
        "bound_exercise_id": result["bound_exercise_id"],
        "alias": result["alias"],
        "exercise_name_zh": result.get("exercise_name_zh") or "",
    }


def list_plan_recommend_gaps(
    session: Session,
    *,
    limit_traces: int = 400,
    top_n: int = 8,
) -> list[dict[str, Any]]:
    """聚合荐计划 0 命中（recommend_miss / recommend_empty）按场景标签。"""
    traces = list(
        session.exec(
            select(DebugTrace).order_by(col(DebugTrace.id).desc()).limit(max(50, min(limit_traces, 1000)))
        ).all()
    )
    buckets: dict[str, dict[str, Any]] = {}

    for trace in traces:
        payload = trace.payload if isinstance(trace.payload, dict) else {}
        grounding = payload.get("grounding") if isinstance(payload.get("grounding"), dict) else {}
        intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
        params = intent.get("params") if isinstance(intent.get("params"), dict) else {}
        branch = str(grounding.get("branch") or "")
        fallback = str(params.get("recommend_fallback") or "")
        plan_kind = str(params.get("plan_kind") or "")
        ids = grounding.get("recommended_plan_ids")
        zero_hits = (
            branch in {"recommend_miss", "recommend_empty"}
            or fallback in {"recommend_miss", "recommend_empty"}
            or (
                plan_kind == "recommend_plan"
                and isinstance(ids, list)
                and len(ids) == 0
            )
        )
        if not zero_hits:
            continue

        scene = (
            grounding.get("plan_scene")
            or params.get("plan_scene")
            or None
        )
        if isinstance(scene, str):
            scene = scene.strip() or None
        else:
            scene = None
        label = scene or "未标明场景"
        key = _norm_query(label) or "unknown"
        created = trace.created_at.isoformat() if isinstance(trace.created_at, datetime) else None
        bucket = buckets.get(key)
        example = (trace.user_text or "").strip()
        if bucket is None:
            buckets[key] = {
                "key": key,
                "label": label,
                "scene_tag": scene,
                "count": 1,
                "last_at": created,
                "examples": [example] if example else [],
                "studio_path": "/studio",
            }
            continue
        bucket["count"] = int(bucket["count"]) + 1
        if created and (not bucket.get("last_at") or created > str(bucket["last_at"])):
            bucket["last_at"] = created
        examples = list(bucket.get("examples") or [])
        if example and example not in examples and len(examples) < 3:
            examples.append(example)
            bucket["examples"] = examples

    items = sorted(
        buckets.values(),
        key=lambda row: (int(row.get("count") or 0), str(row.get("last_at") or "")),
        reverse=True,
    )
    return items[: max(1, min(top_n, 20))]


def resolve_miss(
    session: Session,
    *,
    norm_query: str,
    status: ResolveStatus,
    bound_exercise_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if status not in {"created_sku", "ignored"}:
        raise HTTPException(status_code=400, detail="status 仅支持 created_sku / ignored")
    state = _upsert_miss_state(
        session,
        norm_query=norm_query,
        status=status,
        bound_exercise_id=bound_exercise_id,
        note=note,
    )
    return {
        "ok": True,
        "norm_query": state.norm_query,
        "status": state.status,
        "bound_exercise_id": state.bound_exercise_id,
        "note": state.note,
    }


def list_feedbacks(
    session: Session,
    *,
    status: str | None = "pending",
    limit: int = 50,
) -> list[dict[str, Any]]:
    q = select(FeedbackEvent).where(FeedbackEvent.rating == "down")
    if status and status not in {"", "all"}:
        q = q.where(FeedbackEvent.export_status == status)
    rows = list(
        session.exec(
            q.order_by(col(FeedbackEvent.id).desc()).limit(max(1, min(limit, 200)))
        ).all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "rating": row.rating,
                "tags": list(row.tags or []),
                "note": row.note or "",
                "question": row.question or "",
                "answer": row.answer or "",
                "conversation_id": row.conversation_id or "",
                "trace_id": row.trace_id,
                "assistant_turn_id": row.assistant_turn_id,
                "export_status": row.export_status or "pending",
                "snapshot": row.snapshot or {},
                "ai_diagnosis": row.ai_diagnosis,
            }
        )
    return out


async def diagnose_feedback(session: Session, feedback_id: int) -> dict[str, Any]:
    row = session.get(FeedbackEvent, feedback_id)
    if row is None or row.rating != "down":
        raise HTTPException(status_code=404, detail="差评不存在")
    snap = row.snapshot or {}
    system = (
        "【AI_OPS_FEEDBACK_DIAGNOSE】你是对话质量审稿人。"
        "根据差评快照归因，只返回 JSON："
        '{"root_cause":"wrong_route|missing_alias|plan_constraint|context_lost|bad_answer|other",'
        '"fix_hint":string,"assert_draft":string}'
    )
    user = (
        f"tags={row.tags}\nnote={row.note}\n"
        f"question={row.question}\nanswer={row.answer}\n"
        f"route={snap.get('route')}\nbranch={snap.get('branch')}\n"
        f"intent={snap.get('intent')}\nhistory={snap.get('history')}\n"
    )
    raw: dict[str, Any] = {}
    try:
        from app.brain.llm import TEMPERATURE_STRUCTURED, get_llm

        raw = await get_llm().complete_json(system, user, temperature=TEMPERATURE_STRUCTURED)
    except Exception:
        raw = {}
    if not isinstance(raw, dict) or not raw.get("root_cause"):
        tags = set(row.tags or [])
        if "wrong_route" in tags or "wrong_topic" in tags:
            cause = "wrong_route"
            hint = "核对意图分流与路由断言。"
        elif "multi_turn_lost" in tags:
            cause = "context_lost"
            hint = "补长对话用例，断言上下文是否保留。"
        else:
            cause = "bad_answer"
            hint = "导出 inbox 后补 text / llm-rubric。"
        raw = {
            "root_cause": cause,
            "fix_hint": hint,
            "assert_draft": "type: javascript\nvalue: file://assertions/shape.js",
        }
    diagnosis = {
        "root_cause": str(raw.get("root_cause") or "other"),
        "fix_hint": str(raw.get("fix_hint") or ""),
        "assert_draft": str(raw.get("assert_draft") or ""),
    }
    row.ai_diagnosis = diagnosis
    session.add(row)
    session.commit()
    session.refresh(row)
    return diagnosis


def _load_export_mod():
    script = Path(__file__).resolve().parents[2] / "scripts" / "export_feedback_inbox.py"
    spec = importlib.util.spec_from_file_location("export_feedback_inbox", script)
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail="导出脚本不可用")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def export_feedback_case(
    session: Session,
    feedback_id: int,
    *,
    write_file: bool = True,
    format: Literal["auto", "single", "thread"] = "auto",
) -> dict[str, Any]:
    row = session.get(FeedbackEvent, feedback_id)
    if row is None or row.rating != "down":
        raise HTTPException(status_code=404, detail="差评不存在")
    mod = _load_export_mod()
    doc = mod._case_doc(row, format=format, session=session)
    yaml_text = (
        "# inbox 草稿：未审不进正式绿集。\n"
        + mod._dump_yaml(doc)
        + "\n"
    )
    path_name = None
    if write_file:
        out_dir = Path(__file__).resolve().parents[3] / "eval" / "inbox"
        out_dir.mkdir(parents=True, exist_ok=True)
        fmt = (doc.get("meta") or {}).get("format") or "single"
        slug = mod._slug(row.question or "feedback")
        path = out_dir / f"FB-{row.id}-{fmt}-{slug}.yaml"
        path.write_text(yaml_text, encoding="utf-8")
        path_name = str(path)
    row.export_status = "exported"
    session.add(row)
    session.commit()
    return {"ok": True, "id": row.id, "export_status": "exported", "yaml": yaml_text, "path": path_name}


def discard_feedback(session: Session, feedback_id: int) -> dict[str, Any]:
    row = session.get(FeedbackEvent, feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    row.export_status = "discarded"
    session.add(row)
    session.commit()
    return {"ok": True, "id": row.id, "export_status": "discarded"}
