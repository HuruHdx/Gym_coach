"""后台 AI 补全前的分类启发：禁止用心肺凑抗阻。"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.admin_editor import _guess_taxonomy, _normalize_pattern


def _ex(**kwargs: object) -> SimpleNamespace:
    base = {
        "name_zh": "",
        "name_en": "",
        "muscle": None,
        "sub_region": None,
        "movement_pattern": None,
        "gear": None,
        "modality": "抗阻",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_straight_arm_pulldown_is_vertical_pull_not_cardio():
    g = _guess_taxonomy(_ex(name_zh="直臂下压"))
    assert g["movement_pattern"] == "垂直拉"
    assert g["muscle"] == "背"
    assert g["modality"] == "抗阻"


def test_unknown_name_does_not_default_to_cardio_pattern():
    g = _guess_taxonomy(_ex(name_zh="奇怪新动作xyz"))
    assert g["movement_pattern"] is None
    assert g.get("needs_review") is True
    note = g.get("confidence_note") or ""
    assert "动作模式" in note or "不确定" in note


def test_normalize_pushdown_alias():
    assert _normalize_pattern("直臂下压相关") == "垂直拉"
    assert _normalize_pattern("绳索下压") == "垂直拉"
