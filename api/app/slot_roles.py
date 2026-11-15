"""Infer Exercise.slot_roles from cleaned taxonomy (does not touch muscle `roles`)."""

from __future__ import annotations

from typing import Any

PLAN_SLOT_ROLES = ("main", "assist", "isolation", "warmup")

_ISOLATION_PATTERNS = {
    "肘屈伸(弯举/臂屈伸)",
    "肩孤立(平举)",
    "核心卷曲/稳定",
}
_COMPOUND_PATTERNS = {
    "水平推",
    "垂直推",
    "水平拉",
    "垂直拉",
    "膝主导(蹲)",
    "髋主导(铰链)",
}
_WARMUP_PATTERNS = {
    "拉伸/灵活",
}


def infer_slot_roles(
    *,
    movement_pattern: str | None = None,
    gear: str | None = None,
    modality: str | None = None,
    coach_core: bool = False,
) -> list[str]:
    """Heuristic defaults for plan-slot matching. Safe to overwrite empty rows only."""
    pattern = (movement_pattern or "").strip()
    modality_s = (modality or "").strip()
    gear_s = (gear or "").strip()

    if modality_s == "灵活性" or pattern in _WARMUP_PATTERNS or "拉伸" in pattern:
        return ["warmup"]
    if pattern in _ISOLATION_PATTERNS:
        return ["isolation"]
    if pattern in _COMPOUND_PATTERNS:
        if gear_s == "自由重量" or coach_core:
            return ["main", "assist"]
        return ["assist", "main"]
    if modality_s in ("有氧", "HIIT") or pattern == "全身心肺/综合":
        return ["assist"]
    if coach_core:
        return ["main", "assist"]
    return ["assist"]


def normalize_slot_roles(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        role = str(item or "").strip().lower()
        if role in PLAN_SLOT_ROLES and role not in out:
            out.append(role)
    return out
