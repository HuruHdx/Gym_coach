"""教练荐模板：检索已发布计划 + 库驱动澄清（与今日排课工具分离）。

场景只认库内真实 scene_tag；不按用户口语写死同义词表，不按画像性别筛。
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.services.plan_service import list_published_plans

LEVEL_LABEL = {
    "beginner": "新手",
    "intermediate": "进阶",
    "advanced": "进阶",
}

CUSTOMIZE_TODAY_CHIP = {
    "label": "按部位当场排一场",
    "prompt": "今天按我的情况帮我排一场训练",
}


def aggregate_plan_facets(session: Session) -> dict[str, Any]:
    """当前已发布计划的真实筛选项分布。"""
    cards = list_published_plans(session)
    scenes: dict[str, int] = {}
    levels: dict[str, int] = {}
    days: dict[int, int] = {}
    for card in cards:
        scene = str(card.get("scene_tag") or "").strip()
        if scene:
            scenes[scene] = scenes.get(scene, 0) + 1
        level = str(card.get("level") or "").strip()
        if level:
            levels[level] = levels.get(level, 0) + 1
        dpw = card.get("days_per_week")
        if isinstance(dpw, int) and dpw > 0:
            days[dpw] = days.get(dpw, 0) + 1
    return {
        "total": len(cards),
        "scene_tags": scenes,
        "levels": levels,
        "days_per_week": days,
    }


def published_scene_tags(session: Session) -> list[str]:
    """已发布计划里出现过的场景标签（闭集，供意图模型选用）。"""
    facets = aggregate_plan_facets(session)
    scenes = facets.get("scene_tags") or {}
    return sorted(scenes.keys(), key=lambda s: (-int(scenes.get(s) or 0), s))


def resolve_plan_scene(
    *,
    raw: str,
    facets: dict[str, Any],
    plan_scene: str | None,
) -> str | None:
    """只接受库内 scene_tag：优先意图闭集字段，其次原文是否直接出现该标签名。"""
    scenes = facets.get("scene_tags") or {}
    if not scenes:
        return None
    if isinstance(plan_scene, str):
        tag = plan_scene.strip()
        if tag in scenes:
            return tag
    text = raw or ""
    for scene in scenes:
        if scene and scene in text:
            return scene
    return None


def retrieve_plans(
    session: Session,
    *,
    scene_tag: str | None = None,
    level: str | None = None,
    days_per_week: int | None = None,
    muscles: list[str] | None = None,
    q: str | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """只查已发布计划，按粗匹配打分后取前 limit 张摘要。"""
    cards = list_published_plans(
        session,
        scene_tag=scene_tag if scene_tag and scene_tag != "全部" else None,
        level=level or None,
        muscle=(muscles or [None])[0] if muscles and len(muscles) == 1 else None,
    )
    q_norm = (q or "").strip().lower()
    muscle_set = {str(m).strip() for m in (muscles or []) if m and m != "全身"}
    scored: list[tuple[int, dict[str, Any]]] = []
    for card in cards:
        score = 0
        title = str(card.get("title") or "")
        subtitle = str(card.get("subtitle") or "")
        split = str(card.get("split_summary") or "")
        scene = str(card.get("scene_tag") or "")
        blob = f"{title} {subtitle} {split} {scene}".lower()
        if days_per_week is not None and card.get("days_per_week") == days_per_week:
            score += 3
        if scene_tag and scene == scene_tag:
            score += 4
        if level and card.get("level") == level:
            score += 2
        tags = {str(t) for t in (card.get("muscle_tags") or [])}
        if muscle_set:
            overlap = len(muscle_set & tags)
            score += overlap * 2
        if q_norm:
            if q_norm in blob:
                score += 5
        scored.append((score, card))
    scored.sort(key=lambda x: (-x[0], int(x[1].get("sort_order") or 0), str(x[1].get("id") or "")))
    out: list[dict[str, Any]] = []
    for score, card in scored[: max(1, min(limit, 5))]:
        out.append(
            {
                "id": card.get("id"),
                "title": card.get("title"),
                "subtitle": card.get("subtitle"),
                "scene_tag": card.get("scene_tag"),
                "level": card.get("level"),
                "level_label": card.get("level_label")
                or LEVEL_LABEL.get(str(card.get("level") or ""), card.get("level")),
                "days_per_week": card.get("days_per_week"),
                "minutes_label": card.get("minutes_label"),
                "split_summary": card.get("split_summary"),
                "muscle_tags": list(card.get("muscle_tags") or []),
                "cover_url": card.get("cover_url"),
                "block_count": card.get("block_count"),
                "match_score": score,
            }
        )
    return out


def _item_from_plan(card: dict[str, Any], *, selected: bool = True) -> dict[str, Any]:
    plan_id = str(card.get("id") or "")
    days = card.get("days_per_week")
    minutes = card.get("minutes_label") or "—"
    split = card.get("split_summary") or "—"
    subtitle_bits = []
    if days:
        subtitle_bits.append(f"每周 {days} 天")
    if minutes and minutes != "—":
        subtitle_bits.append(str(minutes))
    if split and split != "—":
        subtitle_bits.append(str(split))
    return {
        "id": f"plan-{plan_id}",
        "title": card.get("title") or plan_id,
        "subtitle": " · ".join(subtitle_bits) if subtitle_bits else (card.get("subtitle") or ""),
        "selected": selected,
        "meta": {
            "plan_id": plan_id,
            "scene_tag": card.get("scene_tag"),
            "level_label": card.get("level_label"),
            "days_per_week": card.get("days_per_week"),
            "minutes_label": card.get("minutes_label"),
            "split_summary": card.get("split_summary"),
            "cover_url": card.get("cover_url"),
            "muscle_tags": list(card.get("muscle_tags") or []),
        },
    }


def build_clarify_suggestions(facets: dict[str, Any]) -> list[dict[str, str]]:
    """仅从库里真实存在且选项 ≥2 的维度生成澄清芯片。"""
    suggestions: list[dict[str, str]] = []
    scenes = facets.get("scene_tags") or {}
    if len(scenes) >= 2:
        for scene, _n in sorted(scenes.items(), key=lambda x: (-x[1], x[0]))[:3]:
            suggestions.append(
                {
                    "label": scene,
                    "prompt": f"推荐一个{scene}方向的训练计划",
                }
            )
    levels = facets.get("levels") or {}
    if len(levels) >= 2 and len(suggestions) < 4:
        for level, label in (
            ("beginner", "新手入门"),
            ("intermediate", "进阶"),
            ("advanced", "进阶强化"),
        ):
            if level in levels and len(suggestions) < 4:
                suggestions.append(
                    {
                        "label": label,
                        "prompt": f"推荐适合{label}的训练计划",
                    }
                )
    days = facets.get("days_per_week") or {}
    if len(days) >= 2 and len(suggestions) < 4:
        for dpw, _n in sorted(days.items(), key=lambda x: (-x[1], x[0]))[:2]:
            suggestions.append(
                {
                    "label": f"每周 {dpw} 练",
                    "prompt": f"推荐每周能练{dpw}天的计划",
                }
            )
    return suggestions[:4]


def related_plan_card_blocks(
    session: Session,
    *,
    muscles: list[str] | None,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """今日草稿后的附卡：按结构化部位取相关模板；无命中则空。"""
    muscle_list = [m for m in (muscles or []) if m and m != "全身"]
    if not muscle_list:
        return []
    hits = retrieve_plans(session, muscles=muscle_list[:1], limit=limit)
    # 至少有一个 muscle_tags 与部位相交才附，避免「全库前两名」乱挂
    filtered: list[dict[str, Any]] = []
    want = set(muscle_list)
    for card in hits:
        tags = {str(t) for t in (card.get("muscle_tags") or [])}
        if tags & want:
            filtered.append(card)
    if not filtered:
        return []
    items = [_item_from_plan(card, selected=i == 0) for i, card in enumerate(filtered[:limit])]
    n = len(items)
    return [
        {
            "kind": "card",
            "card_type": "plan_recommend",
            "title": f"也可跟这 {n} 套相关完整计划",
            "status": "draft",
            "items": items,
            "actions": [],
            "meta": {"source": "plan_recommend_attach", "attached": True},
        }
    ]


def recommend_plans_reply(
    session: Session,
    intent: Any,
) -> dict[str, Any]:
    """返回 blocks + suggestions；可能是澄清、推荐卡、或空库 fallback。"""
    params = dict(getattr(intent, "params", None) or {})
    raw = str(getattr(intent, "raw", "") or "")
    muscles = list(getattr(intent, "muscles", None) or [])
    facets = aggregate_plan_facets(session)
    total = int(facets.get("total") or 0)

    scene_tag = resolve_plan_scene(
        raw=raw,
        facets=facets,
        plan_scene=params.get("plan_scene"),
    )
    # 天数/水平不靠口语词表猜；有则来自意图槽位（由模型填）
    level = params.get("plan_level") if params.get("plan_level") in (
        "beginner",
        "intermediate",
        "advanced",
    ) else None
    days_raw = params.get("plan_days_per_week")
    days_per_week = int(days_raw) if isinstance(days_raw, int) and 2 <= days_raw <= 6 else None

    vague = (
        not scene_tag
        and not level
        and days_per_week is None
        and not muscles
    )

    if total == 0:
        # 空库：不反问、不丢芯片，由图路由兜底直接排今日草稿
        return {
            "blocks": [],
            "suggestions": [],
            "grounding": {"branch": "recommend_empty", "fallback_to_today": True},
        }

    skip_clarify = total <= 4 or not vague
    if vague and total > 4:
        suggestions = build_clarify_suggestions(facets)
        if suggestions:
            suggestions = suggestions + [CUSTOMIZE_TODAY_CHIP]
            return {
                "blocks": [
                    {
                        "kind": "text",
                        "text": "库里有几套可跟计划。先选个方向，我再给你挑合适的；也可以按部位当场排一场。",
                    }
                ],
                "suggestions": suggestions[:5],
                "grounding": {"branch": "recommend_clarify", "facets": facets},
            }

    hits = retrieve_plans(
        session,
        scene_tag=scene_tag,
        level=level,
        days_per_week=days_per_week,
        muscles=muscles or None,
        q=None,
        limit=3,
    )
    if not hits:
        # 有库但无匹配：同样直接兜底今日草稿，不让用户再点一遍
        return {
            "blocks": [],
            "suggestions": [],
            "grounding": {"branch": "recommend_miss", "fallback_to_today": True},
        }

    items = [_item_from_plan(card, selected=i == 0) for i, card in enumerate(hits)]
    n = len(items)
    text = (
        f"为你挑了 {n} 套可跟计划，点进去看详情或直接加入跟练。也可以按部位当场排一场。"
        if skip_clarify or not vague
        else f"按你的方向挑了 {n} 套，可先看详情再决定跟哪套。"
    )
    return {
        "blocks": [
            {"kind": "text", "text": text},
            {
                "kind": "card",
                "card_type": "plan_recommend",
                "title": f"为你挑了 {n} 套可跟计划",
                "status": "draft",
                "items": items,
                "actions": [],
                "meta": {"source": "plan_recommend"},
            },
        ],
        "suggestions": [CUSTOMIZE_TODAY_CHIP],
        "grounding": {
            "branch": "recommend",
            "recommended_plan_ids": [str(c.get("id")) for c in hits if c.get("id")],
            "plan_scene": scene_tag,
        },
    }
