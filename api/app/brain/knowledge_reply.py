"""知识问答。和排课分开：只讲动作，不挑库里的变体，不出训练卡片。"""

from __future__ import annotations

import time
from typing import Any

from sqlmodel import select

from app.brain.llm import TEMPERATURE_COPY, get_llm
from app.tenancy import get_current_profile

KNOWLEDGE_SYSTEM = """【知识问答】
【角色】
你是 Gym Coach 的私人健身教练，只解答动作和训练知识。

【任务】
用口语把问题讲明白。可以讲这块动作练哪里、怎么发力、握法和握距会把侧重点带到哪、和另一类动作差在哪。

【约束】
1) 对学员称呼「你」。不要把档案里的档位、目标当成称呼。
2) 按动作本身回答。不要列举动作库里的变体名单，不要让学员选一条条目，不要提数据库或编号。
3) 不要输出训练卡片，不要写成一堂课的组次安排。
4) 若给了某一条动作的段落，目标肌用段落里的中文，不要换成别的肌群。问做法时用中文复述步骤，不要整句抄英文。
5) 有伤痛时先说风险和能做的降风险办法，不要鼓励冲击大重量，不要做医学诊断。
6) 【训练统计】只在用户问自己的次数、重量、记录时引用。没问就不要提，也不要因为写着「暂无」就说没有来源。
7) 【部位热力/周节奏】有则只在问进度、哪里练得少、明天练啥、恢复时引用；没有记录就说没有，不要编天数或次数。

【格式】
严格只输出 JSON：{"text":"你的中文回复"}

【精简要求】
- 口语化，别写小作文。一个动作「怎么做」控制在 3-5 行内（约 150-250 字），覆盖关键做法和发力要点即可。
- 不堆铺垫、不复述问题、不列大纲。直接说重点。
- 入门建议、对比、注意事项各点到为止，不展开成长段。
"""

DECIDE_SYSTEM = """【个人决策】
【角色】
你是 Gym Coach 的私人健身教练。这一问要你做选择，或给频率、加减、吃法、能不能做这类决定。不是讲解某一个动作怎么做，也不是排一堂课。

【长期记忆】
用户消息里的档案是长期记忆，每一问都在。结论必须用到其中至少一项，并把用到的字段名写进 basis。
basis 只能取这些名字：训练经验、长期目标、每周、伤痛、训练记录、体重、身高、器械偏好。
档案不是「无」时，basis 不能是空数组。
text 里的理由要能对上 basis 里的字段。不要只说「都行」「看你自己」就结束。
不要把档位、目标当称呼。不要排成一堂课（不要同时给出动作名单、组数和重量）。
有伤痛且和这问有关时，basis 带上「伤痛」。问到自己的记录/进度/哪里练得少时，引用【训练统计】与【部位热力/周节奏】；没有记录就说明没有，不要编。

【格式】
严格只输出 JSON：{"basis":["训练经验"],"text":"你的中文回复"}
"""

_BASIS_ALIASES = {
    "训练经验": "训练经验",
    "经验": "训练经验",
    "长期目标": "长期目标",
    "目标": "长期目标",
    "每周": "每周",
    "每周几天": "每周",
    "伤痛": "伤痛",
    "伤": "伤痛",
    "训练记录": "训练记录",
    "记录": "训练记录",
    "体重": "体重",
    "身高": "身高",
    "器械偏好": "器械偏好",
}


def normalize_basis(raw: Any) -> list[str]:
    """把模型填的依据收成档案字段名。不看用户原句。"""
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.replace("、", ",").split(",") if part.strip()]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        name = _BASIS_ALIASES.get(item.strip())
        if name and name not in out:
            out.append(name)
    return out


async def _complete_decision(prompt: str, *, profile_present: bool) -> tuple[str, dict[str, Any]]:
    """档案在时 basis 不能空。空了重试一次，检查的是字段名。"""
    llm = get_llm()
    raw = await llm.complete_json(DECIDE_SYSTEM, prompt, temperature=TEMPERATURE_COPY)
    basis = normalize_basis(raw.get("basis"))
    text = str(raw.get("text") or "").strip()
    if profile_present and not basis:
        raw = await llm.complete_json(
            DECIDE_SYSTEM,
            prompt + "\n\n上一答的 basis 是空的。档案在【长期记忆】里。basis 至少填一个字段名，text 按这些字段重写。",
            temperature=TEMPERATURE_COPY,
        )
        basis = normalize_basis(raw.get("basis"))
        text = str(raw.get("text") or "").strip() or text
    if not text:
        text = "可以说具体一点，我按你的情况说。"
    return text, {"basis": basis, "text": text}


def collect_training_stats(session: Any, intent: Any, question: str, stats_fixture: list[dict] | None = None) -> tuple[str, dict[str, Any]]:
    """点名动作精确取，不够再按部位复用 get_related_stats。不把整张统计表倒进提示词。
    stats_fixture：评测用假数据，传了就优先用它，不查数据库。"""
    from sqlmodel import select

    from app.brain.knowledge import _contained_names
    from app.brain.memory import _format_stat_line
    from app.brain.tools import build_tool_context, execute_tool
    from app.models import ExerciseStats, Profile
    from app.taxonomy import canonicalize_exercise, normalize_exercise_name

    # 评测假数据优先：直接构造 hits，跳过数据库查询
    if stats_fixture:
        hits = [
            {
                "name": item.get("name", ""),
                "last_weight": item.get("last_weight", 0),
                "last_reps": item.get("last_reps", 0),
                "trend": item.get("trend", ""),
            }
            for item in stats_fixture
        ]
        stats_text = "\n".join(
            f"{h['name']}：上次 {h['last_weight']:g}kg × {h['last_reps']}次（{h['trend']}）"
            for h in hits
        )
        payload = {
            "queried": True,
            "filter": {"muscles": list(intent.muscles or []), "names": [h["name"] for h in hits]},
            "tool_calls": [],
            "hits": hits,
        }
        return stats_text, payload

    focus = [str(name) for name in (intent.params.get("focus_exercises") or []) if name]
    contained = _contained_names(normalize_exercise_name(question or ""))
    names: list[str] = []
    for name in focus + contained:
        if name and name not in names:
            names.append(name)
    picked = names[:2]
    rows: list[Any] = []
    seen: set[str] = set()
    for name in picked:
        row = session.exec(
            select(ExerciseStats).where(ExerciseStats.exercise_name == canonicalize_exercise(name))
        ).first()
        if row is not None and row.exercise_name not in seen:
            rows.append(row)
            seen.add(row.exercise_name)

    tool_calls: list[dict[str, Any]] = []
    extra_hits: list[dict[str, Any]] = []
    stats_text = "\n".join(_format_stat_line(row) for row in rows)
    if len(rows) < 3 and list(intent.muscles or []):
        profile = get_current_profile(session)
        ctx = build_tool_context(session, intent, profile)
        args = {"muscles": list(intent.muscles), "limit": 4}
        got = execute_tool("get_related_stats", args, ctx)
        tool_calls = [
            {"tool": item.get("tool"), "args": item.get("args")} for item in ctx.tool_trace[-1:]
        ]
        if got.get("count"):
            extra = str(got.get("text") or "")
            stats_text = "\n".join(part for part in (stats_text, extra) if part)
            for hit in got.get("hits") or []:
                if hit.get("name") not in seen:
                    extra_hits.append(hit)
                    seen.add(str(hit.get("name")))
    hits = [
        {
            "name": row.exercise_name,
            "last_weight": row.last_weight,
            "last_reps": row.last_reps,
            "trend": row.trend,
        }
        for row in rows
    ] + extra_hits
    payload = {
        "queried": bool(rows) or bool(tool_calls),
        "filter": {"muscles": list(intent.muscles or []), "names": picked},
        "tool_calls": tool_calls,
        "hits": hits,
    }
    return stats_text, payload


def format_progress_brief(session: Any) -> str:
    """部位热力 + 本周节奏摘要，供 recall/decide 注入；无记录时明确说暂无。"""
    from datetime import date

    from app.services.analytics_service import build_dashboard

    try:
        dash = build_dashboard(session, today=date.today(), period="week")
    except Exception:  # noqa: BLE001
        return "（暂无训练场次，无法汇总部位热力与周节奏；没有记录不要编数字。）"

    pulse = dash.get("muscle_pulse") or []
    week = dash.get("week") or {}
    lines: list[str] = []
    trained = week.get("trained_days")
    target = week.get("target_days")
    if trained is not None and target is not None:
        lines.append(f"本周已练 {trained}/{target} 天")
    elif not pulse:
        return "（暂无训练场次，无法汇总部位热力与周节奏；没有记录不要编数字。）"

    status_zh = {"fresh": "刚练", "ok": "正常", "overdue": "偏久", "idle": "未练"}
    bits: list[str] = []
    for row in pulse:
        m = row.get("muscle")
        if not m:
            continue
        ds = row.get("days_since")
        st = status_zh.get(str(row.get("status") or ""), str(row.get("status") or ""))
        cnt = row.get("count_30d") or 0
        if ds is None:
            bits.append(f"{m}=未练(30天{cnt}次)")
        else:
            bits.append(f"{m}={ds}天前/{st}(30天{cnt}次)")
    if bits:
        lines.append("部位：" + "；".join(bits))
    return "\n".join(lines) if lines else "（暂无部位热力数据；没有记录不要编数字。）"


def _allow_inline_video(grounding: dict[str, Any], intent: Any) -> bool:
    """仅 kb 单条精确命中才内联示范视频；ask/decide/recall/多候选只挂静态卡。"""
    branch = grounding.get("branch")
    if branch != "kb":
        return False
    qa_kind = str((intent.params or {}).get("qa_kind") or "").strip()
    if qa_kind in ("decide", "recall", "compare"):
        return False
    kb = grounding.get("kb") or {}
    hits = list(kb.get("hits") or [])
    near = list(kb.get("near_miss") or [])
    return len(hits) == 1 and not near


def build_exercise_ref_card(
    session: Any,
    grounding: dict[str, Any],
    intent: Any,
    *,
    limit: int = 3,
    allow_inline_video: bool | None = None,
) -> dict[str, Any] | None:
    """知识问答命中动作时，挂可点进详情的动作卡（无命中则不挂）。

    现状：ask / decide / kb 等分支都可能挂卡（含 near_miss、focus_exercises）。
    内联视频仅在 allow_inline_video 为真时写入 demo/highlight 字段。
    """
    from app.services.public_catalog import media_pack_by_ids, resolve_by_names

    if allow_inline_video is None:
        allow_inline_video = _allow_inline_video(grounding, intent)

    candidates: list[tuple[str, str | None]] = []  # (name, id?)
    kb = grounding.get("kb") or {}
    # 消歧时 hits/near_miss 都挂上，方便用户直接点进示范
    for hit in list(kb.get("hits") or []) + list(kb.get("near_miss") or []):
        name = str(hit.get("name") or "").strip()
        eid = str(hit.get("id") or "").strip() or None
        if name:
            candidates.append((name, eid))
        if len(candidates) >= limit * 2:
            break

    focus = [str(n).strip() for n in (intent.params.get("focus_exercises") or []) if str(n).strip()]
    for name in focus:
        if not any(c[0] == name for c in candidates):
            candidates.append((name, None))

    if not candidates:
        return None

    need_resolve = [name for name, eid in candidates if not eid]
    resolved = resolve_by_names(session, need_resolve) if need_resolve else {}
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for name, eid in candidates:
        hit = resolved.get(name) if not eid else None
        exercise_id = eid or (str(hit["id"]) if hit else None)
        if not exercise_id or exercise_id in seen_ids:
            continue
        seen_ids.add(exercise_id)
        rows.append(
            {
                "id": exercise_id,
                "name_zh": (hit or {}).get("name_zh") or name,
                "thumb_url": (hit or {}).get("thumb_url"),
            }
        )
        if len(rows) >= limit:
            break

    if not rows:
        return None

    packs = media_pack_by_ids(session, [r["id"] for r in rows])
    for row in rows:
        pack = packs.get(row["id"]) or {}
        # 卡片缩略图优先封面图，避免 demo MP4 进 <img>
        row["thumb_url"] = pack.get("cover_url") or pack.get("thumb_url") or row.get("thumb_url")
        row["cover_url"] = pack.get("cover_url")
        row["demo_url"] = pack.get("demo_url") if allow_inline_video else None
        row["highlight_url"] = pack.get("highlight_url") if allow_inline_video else None
        row["muscle"] = pack.get("muscle")
        row["has_video"] = bool(
            allow_inline_video and (row.get("demo_url") or row.get("highlight_url"))
        )

    items = []
    for row in rows:
        muscle = str(row.get("muscle") or "").strip()
        subtitle = "查看示范与要领"
        if muscle:
            subtitle = f"{subtitle} · {muscle}"
        items.append(
            {
                "id": f"ex-{row['id']}",
                "title": row["name_zh"],
                "subtitle": subtitle,
                "selected": True,
                "meta": {
                    "exercise_id": row["id"],
                    "thumb_url": row.get("thumb_url"),
                    "cover_url": row.get("cover_url"),
                    "demo_url": row.get("demo_url"),
                    "highlight_url": row.get("highlight_url"),
                    "has_video": bool(row.get("has_video")),
                    "muscle": row.get("muscle"),
                },
            }
        )
    title = rows[0]["name_zh"] if len(rows) == 1 else f"{len(rows)} 个相关动作"
    return {
        "kind": "card",
        "card_type": "exercise_ref",
        "title": title,
        "status": "draft",
        "items": items,
        "actions": [],
        "meta": {
            "source": "knowledge",
            "inline_video": bool(allow_inline_video and any(r.get("has_video") for r in rows)),
        },
    }


def _with_exercise_card(
    result: dict[str, Any],
    session: Any,
    grounding: dict[str, Any],
    intent: Any,
    *,
    allow_inline_video: bool | None = None,
) -> dict[str, Any]:
    card = build_exercise_ref_card(
        session,
        grounding,
        intent,
        allow_inline_video=allow_inline_video,
    )
    if not card:
        return result
    blocks = list(result.get("blocks") or [])
    blocks.append(card)
    result["blocks"] = blocks
    return result


def knowledge_extra(grounding: dict[str, Any], *, injured: bool) -> str:
    branch = grounding.get("branch")
    passage = str(grounding.get("passage") or "").strip()
    if branch == "kb" and passage:
        guide = (
            "动作要领以这段为准。目标肌用段落里的中文，不要换成别的肌群。"
            "回答「练哪里」时：主肌群必须提到，并至少再提一个协同肌或参与肌群，不要只回一句「主要练X」。"
            "问做法时用中文，不要整句抄英文。\n"
        )
        if injured:
            guide += "学员有伤痛。先说明风险，再给降重量、减小幅度、换成更稳做法。不要鼓励冲击大重量，不要做诊断。\n"
        return "\n\n【这一条动作】\n" + passage + "\n" + guide
    if branch in ("knowledge", "compare") and passage:
        return "\n\n【问题范围】\n" + passage + "\n按上面的范围用口语回答。\n"
    if branch == "search":
        search = grounding.get("search") or {}
        asked = str(search.get("query") or "").strip() or "这一句"
        reason = str((grounding.get("kb") or {}).get("reason") or "")
        lines = [
            f"- {item.get('title') or ''}：{item.get('snippet') or ''}"
            for item in (search.get("results") or [])
        ]
        head = f"用户要问的是：{asked}。只回答这一句，不要改成别的动作。\n"
        if lines:
            return (
                "\n\n"
                + head
                + "【资料】\n"
                + "\n".join(lines)
                + "\n资料没写到这个名字时，仍按教练知识回答原问题，不要把话题换成资料里的别的动作，不要编数字。\n"
            )
        if reason == "anatomy":
            return (
                "\n\n"
                + head
                + "这是肌群名，不是动作条目。讲它在哪、干什么、哪些动作能练到。"
                + "不要说库里有这个动作，不要说没有可靠来源。\n"
            )
        return "\n\n" + head + "没有外部摘录。按教练知识回答原问题，不要编条目编号，不要说没有可靠来源。\n"
    return ""


async def knowledge_reply_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.brain.graph import _finish_reply, _session

    started = time.perf_counter()
    grounding = dict(state.get("grounding") or {})
    branch = grounding.get("branch")
    question = state.get("user_text") or ""

    from app.brain.memory import Intent, build_profile_summary
    from app.brain.memory_context import build_worker_context

    session = _session()
    raw_intent = state.get("intent") or {}
    intent = Intent(
        expert=raw_intent.get("expert") or "chat",
        muscles=list(raw_intent.get("muscles") or []),
        raw=raw_intent.get("raw") or question,
        params=dict(raw_intent.get("params") or {}),
    )

    if branch == "ask":
        text = str(grounding.get("answer") or "").strip() or "你说的是哪一个动作？"
        # 消歧：挂静态多候选卡，不内联视频
        return _with_exercise_card(
            _finish_reply(
                started,
                grounding,
                text,
                suggestions=list(grounding.get("suggestions") or []),
                node="knowledge_reply",
            ),
            session,
            grounding,
            intent,
            allow_inline_video=False,
        )

    # kb「练哪里」也走模型：库只供 passage，不再回固定句。
    # search 无摘要时同样走模型（knowledge_extra 已写明按教练知识答），不回 NO_SOURCE。

    profile = get_current_profile(session)
    profile_text = build_profile_summary(profile)
    stats_text, _stats = collect_training_stats(
        session,
        intent,
        question,
        stats_fixture=state.get("stats_fixture") or None,
    )
    qa_kind = intent.params.get("qa_kind")
    progress_text = ""
    if qa_kind in ("recall", "decide") and not state.get("stats_fixture"):
        progress_text = format_progress_brief(session)

    if qa_kind == "decide":
        progress_block = f"\n【部位热力/周节奏】\n{progress_text}" if progress_text else ""
        prompt = build_worker_context(
            session,
            question,
            state.get("history"),
            None,
            None,
            f"【长期记忆】\n{profile_text}\n【训练统计】\n{stats_text or '（暂无）'}{progress_block}",
            state.get("intent", {}).get("formatted") or "",
        )
        parse_ok = True
        error: str | None = None
        try:
            text, raw = await _complete_decision(prompt, profile_present=profile is not None)
        except Exception as exc:  # noqa: BLE001
            parse_ok = False
            error = str(exc)
            text = f"这句我暂时答不上来：{exc}"
            raw = {"basis": [], "text": text}
        return _with_exercise_card(
            _finish_reply(
                started,
                grounding,
                text,
                model_called=True,
                prompt=prompt,
                raw=raw if parse_ok else {"text": text},
                parse_ok=parse_ok,
                error=error,
                profile_text=profile_text,
                node="knowledge_reply",
            ),
            session,
            grounding,
            intent,
            allow_inline_video=False,
        )

    injured = bool(profile is not None and profile.injuries)
    extra = knowledge_extra(grounding, injured=injured)
    injuries = ""
    if injured and profile is not None:
        injuries = "学员伤痛：" + "、".join(profile.injuries) + "。回答动作时要避开这些风险。\n"
    progress_block = f"【部位热力/周节奏】\n{progress_text}\n" if progress_text else ""
    prompt = build_worker_context(
        session,
        question,
        state.get("history"),
        None,
        None,
        f"【长期记忆】\n{profile_text}\n【训练统计】\n{stats_text or '（暂无）'}\n{progress_block}{injuries}{extra}",
        state.get("intent", {}).get("formatted") or "",
    )
    parse_ok = True
    error: str | None = None
    try:
        raw = await get_llm().complete_json(KNOWLEDGE_SYSTEM, prompt, temperature=TEMPERATURE_COPY)
        text = str(raw.get("text") or "").strip() or "可以说具体一点，我按这个动作给你讲。"
    except Exception as exc:  # noqa: BLE001
        parse_ok = False
        error = str(exc)
        text = f"这句我暂时答不上来：{exc}"
        raw = {"text": text}
    if branch == "kb":
        passage = str(grounding.get("passage") or "")
        zh = passage.split("步骤：", 1)[-1].split("说明：", 1)[0].strip()
        if zh and any("\u4e00" <= ch <= "\u9fff" for ch in zh):
            letters = len([ch for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z")])
            if letters > 40 or ("怎么" in question and "垫" in zh and "垫" not in text):
                text = zh[:220]
    return _with_exercise_card(
        _finish_reply(
            started,
            grounding,
            text,
            model_called=True,
            prompt=prompt,
            raw=raw if parse_ok else {"text": text},
            parse_ok=parse_ok,
            error=error,
            profile_text=profile_text,
            node="knowledge_reply",
        ),
        session,
        grounding,
        intent,
    )
