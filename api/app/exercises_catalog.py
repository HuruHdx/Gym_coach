"""Exercise catalog: openGym retrieve + LLM pick (no spoken hot-word matching)."""

from __future__ import annotations

import json
import random
import re
import threading
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from app.exercise_mapping import (
    COACH_CORE_BY_EN,
    enrich_raw,
    injury_keywords_for,
    matches_injury_keywords,
)
from app.taxonomy import canonicalize_exercise

Modality = Literal["抗阻", "有氧", "HIIT", "灵活性"]
MODALITIES: tuple[Modality, ...] = ("抗阻", "有氧", "HIIT", "灵活性")

_ASSETS_JSON = Path(__file__).resolve().parent.parent / "assets" / "opengym" / "opengym_exercises_with_media.json"

# 已停用口语热词表：点名/排除交给意图模型；排课从库检索候选再由 PLAN 模型选，保留定制感与随机性。
SPOKEN_EXERCISE_ALIASES: list[tuple[str, str]] = []

_EXTRA_MODALITIES: dict[str, list[Modality]] = {
    "壶铃摆荡": ["HIIT"],
    "俯卧撑": ["HIIT"],
    "农夫行走": ["HIIT"],
    "登山者": ["HIIT"],
    "波比": ["HIIT"],
    "开合跳": ["HIIT"],
    "战绳": ["HIIT"],
}

# openGym 里会有「股四头肌」这类解剖名词条目；口语「侧重股四头肌」不能当成点名动作
_ANATOMY_NAME_BLOCKLIST = frozenset(
    {
        "胸",
        "背",
        "肩",
        "腿",
        "臂",
        "核心",
        "全身",
        "腹",
        "股四头肌",
        "股四",
        "腘绳肌",
        "股二头肌",
        "臀大肌",
        "臀中肌",
        "胸大肌",
        "背阔肌",
        "三角肌",
        "腹直肌",
        "斜方肌",
        "竖脊肌",
        "小腿",
        "前臂",
        "肱二头肌",
        "肱三头肌",
    }
)
_MOVE_NAME_HINTS = (
    "推",
    "拉",
    "举",
    "蹲",
    "伸",
    "弯",
    "撑",
    "划",
    "飞",
    "夹",
    "压",
    "硬拉",
    "跑",
    "跳",
    "走",
    "爬",
    "摇",
    "拉伸",
    "下拉",
    "卧",
    "桥",
    "鸟",
    "虫",
    "式",
    "机",
    "铃",
    "索",
    "绳",
    "壶",
    "史密斯",
    "哈克",
    "腿举",
)


def looks_like_exercise_name(name: str) -> bool:
    """Filter anatomy labels; keep short movement names like「深蹲」「硬拉」."""
    n = (name or "").strip()
    if not n or n in _ANATOMY_NAME_BLOCKLIST:
        return False
    if n.endswith("肌") and not any(h in n for h in _MOVE_NAME_HINTS):
        return False
    return True


class ExerciseDetail(TypedDict):
    name: str
    muscle: str
    category: str  # gear: 器械|自由重量|绳索|自重
    tips: str
    modality: NotRequired[Modality]
    roles: NotRequired[list[str]]
    id: NotRequired[str]
    coach_core: NotRequired[bool]
    name_en: NotRequired[str]


_lock = threading.Lock()
_loaded = False
_rows: list[ExerciseDetail] = []
_by_name: dict[str, ExerciseDetail] = {}
_match_needles: list[tuple[str, str]] = []


def _tips_from(row: dict[str, Any]) -> str:
    steps = row.get("instructions_zh") or row.get("instructions_en") or []
    if isinstance(steps, list) and steps:
        return str(steps[0])[:120]
    desc = row.get("description_zh") or row.get("description_en") or ""
    return str(desc)[:120]


def _to_detail(enriched: dict[str, Any]) -> ExerciseDetail:
    name_en = (enriched.get("name_en") or "").strip().lower()
    modality: Modality = enriched["modality"]  # type: ignore[assignment]
    name = enriched["name_zh"]
    preferred = COACH_CORE_BY_EN.get(name_en)
    detail: ExerciseDetail = {
        "name": name,
        "muscle": enriched["muscle"],
        "category": enriched["gear"],
        "tips": _tips_from(enriched),
        "modality": modality,
        "roles": list(enriched["roles"]),
        "id": str(enriched.get("id") or ""),
        "coach_core": bool(enriched.get("coach_core") or preferred),
        "name_en": enriched.get("name_en") or "",
    }
    return detail


def _load_from_json() -> list[ExerciseDetail]:
    if not _ASSETS_JSON.exists():
        return []
    raw = json.loads(_ASSETS_JSON.read_text(encoding="utf-8"))
    out: list[ExerciseDetail] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        out.append(_to_detail(enrich_raw(row)))
    return out


# Mutated in place so `from app.exercises_catalog import EXERCISE_BY_NAME` keeps working.
EXERCISES_DATABASE: list[ExerciseDetail] = []
EXERCISE_BY_NAME: dict[str, ExerciseDetail] = {}


def ensure_loaded() -> None:
    global _loaded, _rows, _by_name, _match_needles
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        _rows = _load_from_json()
        _by_name = {canonicalize_exercise(it["name"]): it for it in _rows}
        # 不再用热词/全库扫用户句；点名由意图模型给出。
        _match_needles = []
        EXERCISES_DATABASE.clear()
        EXERCISES_DATABASE.extend(_rows)
        EXERCISE_BY_NAME.clear()
        EXERCISE_BY_NAME.update(_by_name)
        _loaded = True


def reload_catalog() -> None:
    global _loaded
    with _lock:
        _loaded = False
    ensure_loaded()


def _get_rows() -> list[ExerciseDetail]:
    ensure_loaded()
    return _rows


def _get_by_name() -> dict[str, ExerciseDetail]:
    ensure_loaded()
    return _by_name


def modalities_of(name: str | None = None, detail: ExerciseDetail | None = None) -> list[Modality]:
    row = detail
    if row is None and name:
        row = _get_by_name().get(canonicalize_exercise(name))
    if not row:
        return ["抗阻"]
    primary: Modality = row.get("modality") or "抗阻"  # type: ignore[assignment]
    out: list[Modality] = [primary]
    for extra in _EXTRA_MODALITIES.get(row["name"], []):
        if extra not in out:
            out.append(extra)
    return out


def roles_of(name: str | None = None, detail: ExerciseDetail | None = None) -> list[str]:
    row = detail
    if row is None and name:
        row = _get_by_name().get(canonicalize_exercise(name))
    if not row:
        return []
    roles = row.get("roles")
    if roles:
        return list(roles)
    return [row["muscle"]]


def find_exercises_in_text(text: str) -> list[str]:
    """已停用规则热词；排课点名交给意图模型。保留签名以免调用方炸掉。"""
    return []


def _mention_surfaces(name: str) -> list[str]:
    """Catalog display name + parenthetical + meaningful prefixes（椭圆机步行→椭圆机）。"""
    surfaces = [name]
    for part in re.findall(r"\(([^)]+)\)", name):
        part = part.strip()
        if part and part not in surfaces:
            surfaces.append(part)
    # 前缀：用户说「椭圆机」能对上「椭圆机步行」；最短 3 字避免误伤
    for i in range(len(name) - 1, 2, -1):
        stem = name[:i]
        if stem not in surfaces:
            surfaces.append(stem)
    return surfaces


def find_catalog_mentions_in_text(text: str) -> list[str]:
    """从动作库条目做子串命中（非口语热词表）。供档案「以后别排」/改稿排除。"""
    t = (text or "").strip()
    if not t:
        return []
    ensure_loaded()
    hits: list[tuple[int, str]] = []
    for item in _rows:
        name = item["name"]
        if not looks_like_exercise_name(name):
            continue
        best = 0
        for surface in _mention_surfaces(name):
            if len(surface) < 3:
                continue
            if surface in t and len(surface) > best:
                best = len(surface)
        if best:
            hits.append((best, name))
    hits.sort(key=lambda x: (-x[0], x[1]))
    out: list[str] = []
    for _, name in hits:
        if name not in out:
            out.append(name)
    return out[:12]


def is_banned_for_injuries(title: str, injuries: list[str]) -> bool:
    """Keyword soft-ban (no biomechanical load fields)."""
    t = canonicalize_exercise(title)
    detail = _get_by_name().get(t)
    name_zh = detail["name"] if detail else t
    name_en = (detail or {}).get("name_en") or ""
    keywords = injury_keywords_for(injuries)
    if matches_injury_keywords(name_zh, str(name_en), keywords):
        return True
    for inj in injuries or []:
        if inj and inj.strip() in t:
            return True
    return False


def retrieve_candidates(
    *,
    muscles: list[str] | None = None,
    modalities: list[str] | None = None,
    equipment: list[str] | None = None,
    injuries: list[str] | None = None,
    exclude: list[str] | None = None,
    focus: list[str] | None = None,
    boost_names: list[str] | None = None,
    limit: int = 30,
) -> list[ExerciseDetail]:
    """Small candidate pool for PLAN prompts / swap."""
    ensure_loaded()
    want_mods = [m for m in (modalities or []) if m]
    want_muscles = [m for m in (muscles or []) if m and m != "全身"]
    gear_allow = set(equipment or [])
    exclude_set = {canonicalize_exercise(x) for x in (exclude or []) if x}
    focus_set = {canonicalize_exercise(x) for x in (focus or []) if x}
    boost_set = {canonicalize_exercise(x) for x in (boost_names or []) if x}
    keywords = injury_keywords_for(injuries)

    scored: list[tuple[int, ExerciseDetail]] = []
    for item in _rows:
        name = canonicalize_exercise(item["name"])
        if not looks_like_exercise_name(item["name"]):
            continue
        if name in exclude_set:
            continue
        if want_mods and not any(m in modalities_of(detail=item) for m in want_mods):
            continue
        roles = roles_of(detail=item)
        if want_muscles and not any(m in roles for m in want_muscles):
            continue
        if gear_allow and item["category"] not in gear_allow:
            continue
        if keywords and matches_injury_keywords(item["name"], str(item.get("name_en") or ""), keywords):
            continue

        score = 0
        # 用户点名（模型给出）用子串加权，便于「深蹲」抬起「杠铃深蹲」
        if any(f and (f in item["name"] or item["name"] in f) for f in focus_set):
            score += 100
        if item.get("coach_core"):
            score += 25
        if name in boost_set:
            score += 35
        if len(item["name"]) <= 2:
            score -= 20
        scored.append((score, item))

    # 同档内打乱，避免每次都同一套「最热」动作，保留定制随机感
    by_band: dict[int, list[ExerciseDetail]] = {}
    for score, item in scored:
        by_band.setdefault(score, []).append(item)
    ordered_scores = sorted(by_band.keys(), reverse=True)
    out: list[ExerciseDetail] = []
    seen: set[str] = set()
    for score in ordered_scores:
        band = by_band[score]
        random.shuffle(band)
        for item in band:
            n = item["name"]
            if n in seen:
                continue
            seen.add(n)
            out.append(item)
            if len(out) >= limit:
                return out
    return out


def format_candidates_block(items: list[ExerciseDetail]) -> str:
    if not items:
        return ""
    lines = ["候选动作库："]
    for it in items:
        roles = "/".join(roles_of(detail=it) or [it["muscle"]])
        mod = (it.get("modality") or "抗阻")
        lines.append(f"- {it['name']} | 可作={roles} | 课型={mod} | 器械={it['category']}")
    return "\n".join(lines)


def alternatives(
    muscle: str,
    exclude: str | None = None,
    injuries: list[str] | None = None,
    modality: Modality | None = None,
) -> list[str]:
    details = alternatives_rich(muscle, exclude=exclude, injuries=injuries, modality=modality)
    return [d["name"] for d in details]


def alternatives_rich(
    muscle: str,
    exclude: str | None = None,
    injuries: list[str] | None = None,
    modality: Modality | None = None,
) -> list[ExerciseDetail]:
    ex = canonicalize_exercise(exclude) if exclude else None
    want: Modality | None = modality
    if want is None and ex:
        detail = _get_by_name().get(ex)
        if detail:
            want = detail.get("modality") or "抗阻"  # type: ignore[assignment]
    if want is None:
        want = "抗阻"
    return retrieve_candidates(
        muscles=[muscle] if muscle else None,
        modalities=[want],
        injuries=injuries,
        exclude=[ex] if ex else None,
        limit=40,
    )


def suggest_weight_from_stats(
    last_weight: float | None,
    experience: str,
    last_feeling: str | None = None,
    last_outcome: str | None = None,
) -> float | None:
    if last_weight is None:
        return None
    if last_feeling == "力竭":
        return last_weight
    if last_feeling == "轻松":
        bump = 2.5 if experience in ("进阶", "老炮") else 1.25
        return round(last_weight + bump, 1)
    if last_feeling == "合适":
        return last_weight
    if last_outcome in ("次数未达标", "没做完", "降重完成"):
        return last_weight
    if last_outcome == "超额完成":
        bump = 2.5 if experience in ("进阶", "老炮") else 1.25
        return round(last_weight + bump, 1)
    if last_outcome in ("加重完成", "达标"):
        return last_weight
    return last_weight


# Re-export mapping helpers for import script / tests
__all__ = [
    "MODALITIES",
    "ExerciseDetail",
    "SPOKEN_EXERCISE_ALIASES",
    "EXERCISES_DATABASE",
    "EXERCISE_BY_NAME",
    "modalities_of",
    "roles_of",
    "find_exercises_in_text",
    "find_catalog_mentions_in_text",
    "looks_like_exercise_name",
    "is_banned_for_injuries",
    "retrieve_candidates",
    "format_candidates_block",
    "alternatives",
    "alternatives_rich",
    "suggest_weight_from_stats",
    "ensure_loaded",
    "reload_catalog",
]
