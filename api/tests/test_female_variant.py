"""女版 SKU 派生与候选优先。"""

from __future__ import annotations

from app.exercise_match import prefer_female_candidates
from app.services.admin_editor import female_display_name


def test_female_display_name():
    assert female_display_name("高位下拉") == "高位下拉·女"
    assert female_display_name("高位下拉·女") == "高位下拉·女"
    assert female_display_name("").endswith("·女")


def test_prefer_female_candidates_orders_and_flags():
    cands = [
        {
            "id": "1",
            "name_zh": "高位下拉",
            "score": 100,
            "reason": "同名",
            "is_female_variant": False,
            "has_female_variant": False,
        },
        {
            "id": "2",
            "name_zh": "高位下拉·女",
            "score": 90,
            "reason": "别名",
            "is_female_variant": True,
            "has_female_variant": False,
        },
        {
            "id": "3",
            "name_zh": "窄距下拉",
            "score": 80,
            "reason": "核心",
            "is_female_variant": False,
            "has_female_variant": True,
            "female_variant": "9",
        },
    ]
    out = prefer_female_candidates(cands, prefer_female=True)
    assert out[0]["id"] == "2"
    assert any(c["id"] == "1" and c.get("prefer_derive_female") for c in out)
    male_with_female = next(c for c in out if c["id"] == "3")
    assert male_with_female["score"] == 72
