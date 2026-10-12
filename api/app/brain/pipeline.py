from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.brain.intent_rewrite import build_clarification, needs_clarification, rewrite_intent
from app.brain.llm import get_llm
from app.brain.memory import (
    apply_profile_defaults,
    assemble_memory,
    draft_title_for_intent,
    format_intent_for_prompt,
)
from app.brain.validate import validate_and_build_blocks
from app.models import DebugTrace, Profile
from app.taxonomy import canonicalize_exercise
from app.schemas import AgentReply, Suggestion, TextBlock


SYSTEM_PROMPT = """你是 Gym Coach 的训练助手。根据用户画像与历史，输出 JSON：
{
  "text": "简短中文说明",
  "card": {
    "card_type": "training_draft",
    "title": "背训",
    "items": [
      {"id":"c1","title":"动作名","subtitle":"组次 · 建议重量","selected":true,
       "meta":{"sets":4,"reps":"8-10","weight":30,"muscle":"胸"}}
    ]
  }
}
规则：
- 动作名简洁中文；每个动作 meta 必须含 sets、reps、muscle
- meta.muscle 表示本堂这个动作怎么用，按用户这句话从该动作的「可作」里选；复合动作不要死用目录默认。例：用户要硬拉练背→硬拉标背；直腿硬拉偏股二→标腿；只说深蹲+硬拉→按主动作排，课名不要拼成腿+背
- 换动作、替代也按本堂用途选同类，不要只按目录默认部位硬筛
- 自重动作（俯卧撑、引体向上、平板支撑、卷腹等）不要写 weight
- 只有需要负重的动作才写 weight；无历史时按经验给保守起始重量，不要给自重动作编一个很小的公斤数
- 只有画像里写了伤痛才避开相关高风险动作（腰避高轴向负荷硬拉/杠铃深蹲；膝避深蹲/跳箱/腿屈伸；肩避过头推举）
- 伤痛为无时按正常训练排，不要在说明里写保护膝盖、保护腰、注意关节，也不要因为练腿就主动降阶或拿掉深蹲、硬拉
- 严格遵守「结构化意图」中的部位展开、器械限制、单次时长与疲劳降阶
- 单次时长较短（≤35 分钟）时少排动作、控组数；较长（≥60 分钟）可多 1～2 个辅助动作
- 依据「上次重量」、组数与次数「客观表现」和手动「体感」：
  * 有体感时以体感为准：力竭不加重；轻松 +2.5kg；合适保持。
  * 「上次重量」是该动作这次实际用过的最高重量，下次同一动作以它为基准，组数保持接近上次。
  * 没体感时看表现：没做完、次数未达标、降重完成、达标、加重完成都不在上次重量上再加。超额完成才 +2.5kg。加重完成表示上次已经用了更高的重量。
  * 无历史则按新手体重保守给起始重量。
- 给 3~5 个动作，**全部 selected=true**（列出即默认要练；用户可在前端取消勾选）
- 若结构化意图里有「点名动作」，这些动作必须出现且 selected=true
- 若有「标题=」，card.title 必须原样使用；标题要短：单部位用「背训/胸训」，多部位用「胸+背」，点名动作用「深蹲、硬拉」；禁止写「今日草稿」
- 用户在点名动作之外还要求收尾（腹肌、核心），只加 1 个该收尾动作且 selected=true，不要再塞第二个同类
- 若写了「只排点名动作」，items 里只放这些动作，不要再加别的
- 若附了「当前屏幕上的草稿」，先看说明：点名了新动作就是重排一堂新课，不要沿用上一版的部位标题
- 用户可以点名动作库里的任意动作，不限于胸、背、腿、全身四个方向
- 如果用户是在问问题、核对重量或商量，而不是要重开一堂课：text 里直接回答；已有草稿时 card 按他的修改来，没说改动作就保持原草稿
- 只输出 JSON
"""


def _normalize_card_title(block: Any) -> Any:
    """去掉历史「今日草稿 ·」前缀；单部位补「训」。"""
    if getattr(block, "kind", None) != "card":
        return block
    title = (getattr(block, "title", None) or "").strip()
    if not title:
        return block
    for prefix in ("今日草稿 · ", "今日草稿·", "今日草稿 "):
        if title.startswith(prefix):
            title = title[len(prefix) :].strip()
    singles = {"胸", "背", "肩", "腿", "臂", "核心", "全身"}
    if title in singles:
        title = "全身训" if title == "全身" else f"{title}训"
    if title == block.title:
        return block
    return block.model_copy(update={"title": title})


def _select_all_items(block: Any) -> Any:
    if getattr(block, "kind", None) != "card":
        return block
    items = list(getattr(block, "items", None) or [])
    if not items or all(getattr(it, "selected", False) for it in items):
        return block
    return block.model_copy(
        update={"items": [it.model_copy(update={"selected": True}) for it in items]}
    )


def _draft_prompt(title: str | None, items: list[Any], fresh: bool = False) -> str:
    if not items:
        return ""
    lines = []
    for it in items:
        meta = getattr(it, "meta", None) or {}
        muscle = meta.get("muscle") or ""
        flag = "已勾选" if getattr(it, "selected", True) else "未勾选"
        lines.append(f"- {it.title}（{muscle}，{flag}）")
    head = f"当前屏幕上的草稿：{title}\n" if title else "当前屏幕上的草稿：\n"
    if fresh:
        tail = (
            "\n用户这句点名了新的动作，按这句重排一堂新课。"
            "不要沿用上一版草稿的部位标题，不要把硬拉收成「背」再写成「腿+背」。"
            "上一版里没被这句点到的动作不要保留。标题用结构化意图里的「标题」。\n\n"
        )
    else:
        tail = (
            "\n如果用户是在改这一版（只要某几个、去掉、换成），就在这版上改，不要反问练胸、练背、练腿还是全身。"
            "如果用户是在新开一堂课，按新意图重排，不要把旧草稿里没被点名的动作都留着。\n\n"
        )
    return head + "\n".join(lines) + tail


def _trim_to_request(blocks: list[Any], intent: Any) -> list[Any]:
    """点名的动作留下。收尾只要一个，不要再把上一堂的部位课垫回来。"""
    focus = [canonicalize_exercise(name) for name in (intent.params.get("focus_exercises") or [])]
    if not focus:
        return blocks
    title = draft_title_for_intent(intent) or ""
    addon = "腹肌" if title.endswith("腹肌") else "核心" if title.endswith("核心") else None
    trimmed: list[Any] = []
    for block in blocks:
        if getattr(block, "kind", None) != "card":
            trimmed.append(block)
            continue
        kept = []
        addon_item = None
        for item in block.items:
            name = canonicalize_exercise(item.title)
            if name in focus:
                kept.append(item.model_copy(update={"selected": True}))
                continue
            muscle = str((item.meta or {}).get("muscle") or "")
            is_addon = bool(
                addon
                and (
                    addon in item.title
                    or (addon == "腹肌" and (muscle == "核心" or "腹" in item.title))
                    or (addon == "核心" and muscle == "核心")
                )
            )
            if is_addon and addon_item is None and item.selected:
                addon_item = item
        if addon and addon_item is None:
            for item in block.items:
                muscle = str((item.meta or {}).get("muscle") or "")
                if addon == "腹肌" and (muscle == "核心" or "腹" in item.title):
                    addon_item = item.model_copy(update={"selected": True})
                    break
                if addon == "核心" and muscle == "核心":
                    addon_item = item.model_copy(update={"selected": True})
                    break
        if addon_item is not None:
            kept.append(addon_item)
        trimmed.append(block.model_copy(update={"items": kept}))
    return trimmed


async def run_chat_pipeline(
    session: Session,
    user_text: str,
    draft_items: list[Any] | None = None,
    draft_title: str | None = None,
) -> AgentReply:
    profile = session.exec(select(Profile).limit(1)).first()
    # 意图改写：可插拔模型槽（默认 hybrid = 模型 + 规则兜底）
    intent = await rewrite_intent(user_text)
    intent = apply_profile_defaults(intent, profile)
    intent_line = format_intent_for_prompt(intent)

    draft_items = draft_items or []
    # 没点明练哪、也不是在改已有草稿：只反问，不排课
    if needs_clarification(intent, has_draft=bool(draft_items)):
        text, options = build_clarification(intent)
        blocks = [TextBlock(text=text)]
        suggestions = [Suggestion(label=o["label"], prompt=o["prompt"]) for o in options]
        trace = DebugTrace(
            user_text=user_text,
            payload={
                "intent": {
                    "expert": intent.expert,
                    "muscles": intent.muscles,
                    "params": intent.params,
                    "formatted": intent_line,
                },
                "clarification": True,
                "suggestions": [s.model_dump() for s in suggestions],
                "blocks": [b.model_dump() for b in blocks],
            },
        )
        session.add(trace)
        session.commit()
        session.refresh(trace)
        return AgentReply(blocks=blocks, suggestions=suggestions, trace_id=trace.id)

    memory = assemble_memory(session, intent, profile)

    user_prompt = (
        f"用户说：{user_text}\n"
        f"结构化意图：{intent_line}\n\n"
        f"{_draft_prompt(draft_title, draft_items, fresh=bool(intent.params.get('focus_exercises')))}"
        f"{memory.as_prompt_block()}"
    )

    llm = get_llm()
    raw: dict[str, Any]
    parse_ok = True
    error: str | None = None
    try:
        raw = await llm.complete_json(SYSTEM_PROMPT, user_prompt)
    except Exception as e:  # noqa: BLE001
        parse_ok = False
        error = str(e)
        raw = {
            "text": f"生成失败：{e}",
            "card": {"card_type": "training_draft", "title": "草稿", "items": []},
        }

    injuries = profile.injuries if profile else []
    blocks = validate_and_build_blocks(raw, injuries)
    titled = draft_title_for_intent(intent)
    if titled:
        blocks = [
            block.model_copy(update={"title": titled}) if getattr(block, "kind", None) == "card" else block
            for block in blocks
        ]
    # 短课名兜底：模型若仍吐「今日草稿 · 背」→ 收成「背训」
    blocks = [_normalize_card_title(block) for block in blocks]
    # 列出即默认勾选
    blocks = [_select_all_items(block) for block in blocks]
    if intent.params.get("focus_exercises"):
        blocks = _trim_to_request(blocks, intent)

    trace = DebugTrace(
        user_text=user_text,
        payload={
            "intent": {
                "expert": intent.expert,
                "muscles": intent.muscles,
                "params": intent.params,
                "formatted": intent_line,
            },
            "memory": {
                "profile_summary": memory.profile_summary,
                "derived": memory.derived_summaries,
                "logs": memory.recent_logs,
                "token_estimate": memory.token_estimate,
            },
            "prompt_user": user_prompt,
            "raw": raw,
            "parse_ok": parse_ok,
            "error": error,
            "blocks": [b.model_dump() for b in blocks],
        },
    )
    session.add(trace)
    session.commit()
    session.refresh(trace)

    return AgentReply(blocks=blocks, trace_id=trace.id)
