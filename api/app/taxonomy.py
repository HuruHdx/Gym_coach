"""Canonical taxonomy for muscles and exercise name normalization."""

from __future__ import annotations

import re
from enum import Enum


class Muscle(str, Enum):
    CHEST = "胸"
    BACK = "背"
    SHOULDER = "肩"
    LEG = "腿"
    ARM = "臂"
    CORE = "核心"
    FULL = "全身"


MUSCLE_ALIASES: dict[str, Muscle] = {
    "胸": Muscle.CHEST,
    "胸部": Muscle.CHEST,
    "卧推": Muscle.CHEST,
    "背": Muscle.BACK,
    "背部": Muscle.BACK,
    "肩": Muscle.SHOULDER,
    "肩膀": Muscle.SHOULDER,
    "腿": Muscle.LEG,
    "下肢": Muscle.LEG,
    "臀": Muscle.LEG,
    "臂": Muscle.ARM,
    "手臂": Muscle.ARM,
    "二头": Muscle.ARM,
    "三头": Muscle.ARM,
    "核心": Muscle.CORE,
    "腹": Muscle.CORE,
    "全身": Muscle.FULL,
    "上半身": Muscle.CHEST,  # coarse; intent may expand to multi
}


def normalize_muscle(raw: str | None) -> Muscle | None:
    if not raw:
        return None
    key = raw.strip().lower()
    for alias, muscle in MUSCLE_ALIASES.items():
        if alias in key or key in alias:
            return muscle
    return None


def normalize_exercise_name(name: str) -> str:
    """Collapse spacing/punctuation; keep Chinese as-is for display key."""
    s = name.strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("（", "(").replace("）", ")")
    return s


# Common synonym groups → canonical display name
EXERCISE_CANONICAL: dict[str, str] = {
    "哑铃平板卧推": "哑铃卧推",
    "哑铃平卧推": "哑铃卧推",
    "杠铃平板卧推": "杠铃卧推",
    "坐姿器械夹胸": "器械夹胸",
}


def canonicalize_exercise(name: str) -> str:
    n = normalize_exercise_name(name)
    return EXERCISE_CANONICAL.get(n, n)
