"""荐模板：库内场景闭集 + 按部位附卡（无口语硬匹配 / 无性别加权）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.brain.plan_recommend import (
    related_plan_card_blocks,
    resolve_plan_scene,
    retrieve_plans,
)


def _card(plan_id: str, scene: str, *, muscles: list[str] | None = None, sort_order: int = 0) -> dict:
    return {
        "id": plan_id,
        "title": f"计划{plan_id}",
        "subtitle": "",
        "scene_tag": scene,
        "level": "beginner",
        "level_label": "新手",
        "days_per_week": 3,
        "minutes_label": "45 分钟",
        "split_summary": "三分化",
        "muscle_tags": list(muscles or ["胸", "背"]),
        "cover_url": None,
        "block_count": 3,
        "sort_order": sort_order,
    }


SAMPLE = [
    _card("hot", "热门计划", muscles=["胸", "背"], sort_order=1),
    _card("female", "女性专项", muscles=["臀", "腿"], sort_order=2),
    _card("chest", "增肌专项", muscles=["胸"], sort_order=3),
]


def test_resolve_plan_scene_only_accepts_library_tags():
    facets = {"scene_tags": {"女性专项": 2, "热门计划": 5}}
    assert resolve_plan_scene(raw="随便", facets=facets, plan_scene="女性专项") == "女性专项"
    assert resolve_plan_scene(raw="随便", facets=facets, plan_scene="男生专属") is None
    assert resolve_plan_scene(raw="我想要女性专项", facets=facets, plan_scene=None) == "女性专项"
    # 口语同义词不算：必须模型填闭集或原文出现库内标签名
    assert resolve_plan_scene(raw="给我女生计划", facets=facets, plan_scene=None) is None


def test_retrieve_plans_by_muscle_without_keyword_q():
    with patch("app.brain.plan_recommend.list_published_plans", return_value=SAMPLE):
        hits = retrieve_plans(None, muscles=["胸"], limit=2)  # type: ignore[arg-type]
    assert hits
    # 有胸标签的排前；不靠口语 q 词表
    assert hits[0]["id"] in {"hot", "chest"}
    assert "胸" in (hits[0].get("muscle_tags") or [])
    assert hits[0]["match_score"] >= 2


def test_related_plan_card_blocks_skips_when_no_muscle_overlap():
    only_back = [_card("back", "热门计划", muscles=["背"], sort_order=1)]
    with patch("app.brain.plan_recommend.list_published_plans", return_value=only_back):
        assert related_plan_card_blocks(None, muscles=["胸"], limit=2) == []  # type: ignore[arg-type]


def test_related_plan_card_blocks_attaches_on_overlap():
    with patch("app.brain.plan_recommend.list_published_plans", return_value=SAMPLE):
        blocks = related_plan_card_blocks(None, muscles=["胸"], limit=2)  # type: ignore[arg-type]
    assert len(blocks) == 1
    assert blocks[0]["card_type"] == "plan_recommend"
    assert blocks[0]["meta"]["attached"] is True
    assert blocks[0]["items"]


def test_recommend_empty_and_miss_fallback_to_today_without_chips():
    from app.brain.plan_recommend import recommend_plans_reply

    intent = SimpleNamespace(raw="适合我的计划", muscles=[], params={"plan_kind": "recommend_plan"})
    with patch("app.brain.plan_recommend.list_published_plans", return_value=[]):
        empty = recommend_plans_reply(None, intent)  # type: ignore[arg-type]
    assert empty["grounding"]["fallback_to_today"] is True
    assert empty["blocks"] == []
    assert empty["suggestions"] == []

    with patch("app.brain.plan_recommend.list_published_plans", return_value=SAMPLE):
        with patch("app.brain.plan_recommend.retrieve_plans", return_value=[]):
            miss = recommend_plans_reply(None, intent)  # type: ignore[arg-type]
    assert miss["grounding"]["fallback_to_today"] is True
    assert miss["suggestions"] == []
