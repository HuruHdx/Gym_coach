"""Enrich openGym exercises: stage1 rules (all) + optional stage2 LLM (coach_core).

Usage (from api/):
  uv run python scripts/enrich_opengym_exercises.py
  uv run python scripts/enrich_opengym_exercises.py --llm
  uv run python scripts/enrich_opengym_exercises.py --llm --limit 30
  uv run python scripts/enrich_opengym_exercises.py --report-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.exercise_mapping import (  # noqa: E402
    COACH_CORE_BY_EN,
    enrich_raw,
    map_gear,
    map_modality,
    map_muscle,
    map_roles,
)

SRC = ROOT / "assets" / "opengym" / "opengym_exercises_with_media.json"
OUT = ROOT / "assets" / "opengym" / "opengym_exercises_enriched.json"
REPORT = ROOT / "assets" / "opengym" / "cleaning_report.md"
CACHE = ROOT / "assets" / "opengym" / "_llm_enrich_cache.json"

MUSCLE_WHITELIST = {"胸", "背", "肩", "腿", "臂", "核心", "全身"}
SUB_REGION_WHITELIST = {
    "上胸",
    "中胸",
    "下胸",
    "胸中缝/内侧",
    "胸部整体",
    "背阔肌/背宽",
    "中上背/背厚",
    "下背/竖脊肌",
    "斜方肌",
    "肩前束",
    "肩中束",
    "肩后束",
    "肩袖/稳定",
    "肩部整体",
    "股四头肌(前侧)",
    "腘绳肌(后侧)",
    "臀部",
    "内收/外展肌",
    "小腿",
    "腿部整体",
    "肱二头肌",
    "肱三头肌",
    "前臂",
    "上腹/腹直肌",
    "下腹",
    "腹斜肌(侧腹)",
    "核心抗旋/稳定",
    "心肺有氧",
    "全身爆发/HIIT",
    "全身拉伸/灵活",
}
PATTERN_WHITELIST = {
    "水平推",
    "垂直推",
    "水平拉",
    "垂直拉",
    "膝主导(蹲)",
    "髋主导(铰链)",
    "肘屈伸(弯举/臂屈伸)",
    "肩孤立(平举)",
    "核心卷曲/稳定",
    "全身心肺/综合",
    "拉伸/灵活",
}
STRESS_LEVELS = {"low", "medium", "high"}

ANATOMY_BLOCK = frozenset(
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

COMMON_GEAR = {
    "barbell",
    "dumbbell",
    "cable",
    "body weight",
    "leverage machine",
    "smith machine",
    "ez barbell",
    "kettlebell",
    "trap bar",
    "olympic barbell",
    "assisted",
    "weighted",
    "sled machine",
}

CORE_NAME_HINTS = (
    "bench press",
    "incline bench",
    "decline bench",
    "chest press",
    "chest fly",
    "cable crossover",
    "pec deck",
    "push-up",
    "pushup",
    "dip",
    "pull-up",
    "chin-up",
    "lat pulldown",
    "seated row",
    "bent over row",
    "t-bar row",
    "face pull",
    "shrug",
    "deadlift",
    "romanian",
    "good morning",
    "hyperextension",
    "squat",
    "leg press",
    "leg extension",
    "leg curl",
    "lunge",
    "split squat",
    "hip thrust",
    "glute bridge",
    "calf raise",
    "shoulder press",
    "overhead press",
    "military press",
    "arnold press",
    "lateral raise",
    "front raise",
    "rear delt",
    "reverse fly",
    "upright row",
    "barbell curl",
    "dumbbell curl",
    "hammer curl",
    "preacher curl",
    "triceps extension",
    "skull crusher",
    "pushdown",
    "kickback",
    "close-grip bench",
    "crunch",
    "sit-up",
    "plank",
    "leg raise",
    "russian twist",
    "ab wheel",
    "dead bug",
    "bird dog",
    "mountain climber",
    "burpee",
    "kettlebell swing",
    "farmers walk",
    "clean",
    "snatch",
)

NOISE_HINTS = (
    "bosu",
    "stability ball",
    "exercise ball",
    "swiss ball",
    "medicine ball",
    "on ball",
    "roller",
    "tire",
    "macebell",
    "sandbag",
    "wheel roller",
    "upper body ergometer",
    "skierg",
    "stepmill",
    "elliptical",
    "stationary bike",
    "with twist on",
    "lying on floor with",
)


def _en(row: dict[str, Any]) -> str:
    return (row.get("name_en") or "").strip().lower()


def _zh(row: dict[str, Any]) -> str:
    return (row.get("name_zh") or "").strip()


def is_valid_exercise(row: dict[str, Any]) -> bool:
    name = _zh(row) or _en(row)
    if not name:
        return False
    if name in ANATOMY_BLOCK:
        return False
    if name.endswith("肌") and len(name) <= 4:
        return False
    return True


def derive_sub_region(row: dict[str, Any], muscle: str) -> str:
    en = _en(row)
    target = (row.get("target") or "").strip().lower()

    if muscle == "胸":
        if any(k in en for k in ("incline", "low to high", "low-to-high")):
            return "上胸"
        if any(k in en for k in ("decline", "high to low", "high-to-low")) or (
            "dip" in en and "triceps" not in en
        ):
            return "下胸"
        if any(k in en for k in ("fly", "crossover", "pec deck", "squeeze")):
            return "胸中缝/内侧"
        if target == "pectorals":
            return "中胸"
        return "胸部整体"

    if muscle == "背":
        if target in ("spine",) or any(
            k in en for k in ("hyperextension", "good morning", "back extension")
        ):
            return "下背/竖脊肌"
        if target == "traps" or "shrug" in en:
            return "斜方肌"
        if any(k in en for k in ("pulldown", "pull-up", "pullup", "chin-up", "chinup", "pullover")):
            return "背阔肌/背宽"
        if "row" in en or target in ("upper back", "lats"):
            if "row" in en or target == "upper back":
                return "中上背/背厚"
            return "背阔肌/背宽"
        if target == "lats":
            return "背阔肌/背宽"
        return "中上背/背厚"

    if muscle == "肩":
        if any(k in en for k in ("rear delt", "reverse fly", "face pull", "bent over lateral")):
            return "肩后束"
        if "lateral raise" in en or "side raise" in en:
            return "肩中束"
        if "front raise" in en:
            return "肩前束"
        if any(k in en for k in ("external rotation", "internal rotation", "cuff")):
            return "肩袖/稳定"
        if any(k in en for k in ("press", "overhead", "military", "arnold")):
            return "肩部整体"
        return "肩部整体"

    if muscle == "腿":
        if target == "calves" or "calf" in en:
            return "小腿"
        if target in ("abductors", "adductors") or any(
            k in en for k in ("abduct", "adduct", "hip adduction", "hip abduction")
        ):
            return "内收/外展肌"
        if target == "glutes" or any(
            k in en for k in ("hip thrust", "glute bridge", "kickback", "donkey kick")
        ):
            return "臀部"
        if target == "hamstrings" or any(
            k in en for k in ("romanian", "stiff leg", "straight leg deadlift", "leg curl", "nordic")
        ):
            return "腘绳肌(后侧)"
        if target == "quads" or any(
            k in en for k in ("squat", "leg press", "leg extension", "lunge", "split squat")
        ):
            return "股四头肌(前侧)"
        return "腿部整体"

    if muscle == "臂":
        if target == "forearms" or "wrist" in en or "forearm" in en:
            return "前臂"
        if target == "triceps" or any(
            k in en
            for k in (
                "triceps",
                "pushdown",
                "skull",
                "kickback",
                "overhead extension",
                "close-grip",
                "close grip",
            )
        ):
            return "肱三头肌"
        return "肱二头肌"

    if muscle == "核心":
        if any(k in en for k in ("plank", "dead bug", "bird dog", "pallof", "ab wheel", "rollout")):
            return "核心抗旋/稳定"
        if any(k in en for k in ("twist", "oblique", "side bend", "russian", "woodchop")):
            return "腹斜肌(侧腹)"
        if any(k in en for k in ("leg raise", "knee raise", "reverse crunch", "hanging")):
            return "下腹"
        return "上腹/腹直肌"

    if muscle == "全身":
        modality = map_modality(row.get("category"))
        if modality == "灵活性" or any(k in en for k in ("stretch", "yoga", "mobility")):
            return "全身拉伸/灵活"
        if modality in ("HIIT", "有氧") or any(
            k in en for k in ("burpee", "run", "bike", "jump", "swing", "clean", "snatch")
        ):
            if any(k in en for k in ("run", "bike", "row", "walk", "elliptical", "cardio")):
                return "心肺有氧"
            return "全身爆发/HIIT"
        return "心肺有氧"

    return {
        "胸": "胸部整体",
        "背": "中上背/背厚",
        "肩": "肩部整体",
        "腿": "腿部整体",
        "臂": "肱二头肌",
        "核心": "上腹/腹直肌",
        "全身": "心肺有氧",
    }.get(muscle, "胸部整体")


def derive_movement_pattern(row: dict[str, Any], muscle: str) -> str:
    en = _en(row)
    category = (row.get("category") or "").lower()

    if category in ("stretching", "yoga", "mobility", "pilates") or "stretch" in en:
        return "拉伸/灵活"
    if any(k in en for k in ("burpee", "jumping jack", "mountain climber", "swing", "clean", "snatch")):
        return "全身心肺/综合"
    if muscle == "全身" and map_modality(row.get("category")) in ("有氧", "HIIT"):
        return "全身心肺/综合"

    if any(k in en for k in ("bench press", "chest press", "push-up", "pushup", "fly", "crossover")):
        if "overhead" in en or "shoulder press" in en:
            return "垂直推"
        return "水平推"
    if any(k in en for k in ("shoulder press", "overhead press", "military press", "arnold", "push press")):
        return "垂直推"
    if any(k in en for k in ("pulldown", "pull-up", "pullup", "chin-up", "chinup", "pullover")):
        return "垂直拉"
    if "row" in en or "face pull" in en:
        return "水平拉"
    if any(k in en for k in ("deadlift", "romanian", "good morning", "hip thrust", "kettlebell swing", "hinge")):
        return "髋主导(铰链)"
    if any(k in en for k in ("squat", "leg press", "lunge", "split squat", "step up", "leg extension")):
        return "膝主导(蹲)"
    if any(k in en for k in ("curl", "extension", "pushdown", "skull", "kickback", "dip")):
        return "肘屈伸(弯举/臂屈伸)"
    if any(k in en for k in ("lateral raise", "front raise", "rear delt", "reverse fly")):
        return "肩孤立(平举)"
    if muscle == "核心":
        return "核心卷曲/稳定"
    if muscle == "胸":
        return "水平推"
    if muscle == "背":
        return "水平拉" if "row" in en else "垂直拉"
    if muscle == "腿":
        return "膝主导(蹲)"
    if muscle == "肩":
        return "垂直推"
    if muscle == "臂":
        return "肘屈伸(弯举/臂屈伸)"
    return "全身心肺/综合"


def derive_joint_stress(row: dict[str, Any]) -> dict[str, str]:
    en = _en(row)
    stress = {
        "waist": "low",
        "knee": "low",
        "shoulder": "low",
        "wrist": "low",
        "elbow": "low",
    }
    if any(
        k in en
        for k in (
            "deadlift",
            "good morning",
            "hyperextension",
            "bent over row",
            "bent-over",
            "romanian",
            "clean",
            "snatch",
        )
    ):
        stress["waist"] = "high"
    elif any(k in en for k in ("squat", "overhead press", "farmers", "plank")):
        stress["waist"] = "medium"

    if any(k in en for k in ("squat", "lunge", "jump", "leg extension", "leg press", "split squat")):
        stress["knee"] = "high" if any(k in en for k in ("jump", "leg extension")) else "medium"
        if "jump" in en or "plyo" in en:
            stress["knee"] = "high"

    if any(
        k in en
        for k in (
            "overhead",
            "behind the neck",
            "upright row",
            "dip",
            "handstand",
            "snatch",
            "military press",
        )
    ):
        stress["shoulder"] = "high"
    elif any(k in en for k in ("bench press", "shoulder press", "lateral raise", "pull-up", "pulldown")):
        stress["shoulder"] = "medium"

    if any(k in en for k in ("barbell bench", "barbell curl", "wrist", "clean")):
        stress["wrist"] = "medium"
    if any(k in en for k in ("skull", "close-grip", "close grip", "dip", "pushdown")):
        stress["elbow"] = "medium"
    return stress


def score_coach_core(row: dict[str, Any]) -> int:
    en = _en(row)
    eq = (row.get("equipment") or "").strip().lower()
    score = 0
    if en in COACH_CORE_BY_EN:
        return 1000
    if eq in COMMON_GEAR:
        score += 20
    if any(h in en for h in CORE_NAME_HINTS):
        score += 40
    if any(n in en for n in NOISE_HINTS):
        score -= 50
    # prefer shorter, canonical names
    words = en.split()
    if len(words) <= 4:
        score += 15
    elif len(words) >= 8:
        score -= 20
    if any(k in en for k in ("one arm", "single leg", "on bench", "kneeling", "seated on")):
        score -= 8
    if eq in ("barbell", "dumbbell", "cable", "body weight", "leverage machine", "smith machine"):
        score += 10
    if row.get("image_start"):
        score += 5
    return score


def pick_coach_core(rows: list[dict[str, Any]], target_n: int = 280) -> set[str]:
    """Pick ~target_n coach_core ids with coverage across muscles."""
    forced = {r["id"] for r in rows if _en(r) in COACH_CORE_BY_EN}
    candidates: list[tuple[int, str, str]] = []
    for r in rows:
        if not r.get("is_valid_exercise", True):
            continue
        rid = str(r["id"])
        if rid in forced:
            continue
        s = score_coach_core(r)
        if s < 45:
            continue
        candidates.append((s, r.get("muscle") or "全身", rid))
    candidates.sort(reverse=True)

    # diversify by muscle
    picked = set(forced)
    per_muscle: dict[str, int] = defaultdict(int)
    soft_cap = max(35, target_n // 6)
    for score, muscle, rid in candidates:
        if len(picked) >= target_n:
            break
        if per_muscle[muscle] >= soft_cap and score < 70:
            continue
        picked.add(rid)
        per_muscle[muscle] += 1

    # fill if under target
    for score, muscle, rid in candidates:
        if len(picked) >= target_n:
            break
        picked.add(rid)
    return picked


def stage1_enrich(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for raw in raw_list:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        base = enrich_raw(raw)
        muscle = base["muscle"]
        if muscle not in MUSCLE_WHITELIST:
            muscle = map_muscle(raw.get("body_part"), raw.get("target"))
        roles = map_roles(raw.get("name_en"), muscle)
        # expand roles from secondary_muscles
        from app.exercise_mapping import TARGET_TO_MUSCLE

        for sec in raw.get("secondary_muscles") or []:
            m = TARGET_TO_MUSCLE.get(str(sec).strip().lower())
            if m and m not in roles:
                roles.append(m)
        sub = derive_sub_region(raw, muscle)
        pattern = derive_movement_pattern(raw, muscle)
        stress = derive_joint_stress(raw)
        valid = is_valid_exercise(raw)
        # preferred display name from existing map
        en_key = _en(raw)
        preferred = COACH_CORE_BY_EN.get(en_key)
        name_zh = preferred or (raw.get("name_zh") or raw.get("name_en") or "")

        row = {
            **raw,
            "name_zh": name_zh,
            "muscle": muscle,
            "sub_region": sub if sub in SUB_REGION_WHITELIST else sub,
            "roles": roles,
            "movement_pattern": pattern if pattern in PATTERN_WHITELIST else "全身心肺/综合",
            "gear": map_gear(raw.get("equipment")),
            "modality": map_modality(raw.get("category")),
            "coach_core": False,
            "aliases": [],
            "joint_stress": stress,
            "cues_zh": [],
            "common_mistakes_zh": [],
            "is_valid_exercise": valid,
            "enrich_stage": 1,
        }
        # keep existing zh instructions if present
        if not row.get("instructions_zh"):
            row["instructions_zh"] = []
        enriched.append(row)

    core_ids = pick_coach_core(enriched, target_n=280)
    for row in enriched:
        row["coach_core"] = str(row["id"]) in core_ids
    return enriched


def _clamp_enum(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("muscle") not in MUSCLE_WHITELIST:
        row["muscle"] = "全身"
    if row.get("sub_region") not in SUB_REGION_WHITELIST:
        # fallback by muscle
        defaults = {
            "胸": "胸部整体",
            "背": "中上背/背厚",
            "肩": "肩部整体",
            "腿": "腿部整体",
            "臂": "肱二头肌",
            "核心": "上腹/腹直肌",
            "全身": "心肺有氧",
        }
        row["sub_region"] = defaults.get(row["muscle"], "心肺有氧")
    if row.get("movement_pattern") not in PATTERN_WHITELIST:
        row["movement_pattern"] = "全身心肺/综合"
    js = row.get("joint_stress") or {}
    clean = {}
    for k in ("waist", "knee", "shoulder", "wrist", "elbow"):
        v = str(js.get(k, "low")).lower()
        clean[k] = v if v in STRESS_LEVELS else "low"
    row["joint_stress"] = clean
    return row


LLM_SYSTEM = """你是一位拥有 15 年一线执教经验的 CSCS 认证体能教练与运动解剖学专家。
请根据输入的英文动作数据，对该健身动作进行专业级结构化清洗与中文教案重塑。
必须严格返回 JSON 数组（不要 markdown 代码围栏），每个元素字段：
1. id: 原样返回动作 ID（字符串）
2. name_zh: 中国大陆健身房最地道标准中文名（简洁，不要括号堆砌）
3. aliases: 字符串数组 3~5 个（口语俗称/简称/英文缩写）
4. sub_region: 必须从下列枚举选 1 个：
上胸|中胸|下胸|胸中缝/内侧|胸部整体|背阔肌/背宽|中上背/背厚|下背/竖脊肌|斜方肌|肩前束|肩中束|肩后束|肩袖/稳定|肩部整体|股四头肌(前侧)|腘绳肌(后侧)|臀部|内收/外展肌|小腿|腿部整体|肱二头肌|肱三头肌|前臂|上腹/腹直肌|下腹|腹斜肌(侧腹)|核心抗旋/稳定|心肺有氧|全身爆发/HIIT|全身拉伸/灵活
5. instructions_zh: 长度 4 的字符串数组（每步 15~35 字）：准备握距站距 / 启动向心 / 顶峰落点 / 离心呼吸
6. cues_zh: 长度 2，画面感发力提示
7. common_mistakes_zh: 长度 2，格式「错误表现：后果与纠正」
8. joint_stress: 对象，键 waist/knee/shoulder/wrist/elbow，值只能是 low|medium|high
"""


def _load_cache() -> dict[str, Any]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _call_llm(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import httpx

    from app.config import settings

    compact = []
    for r in batch:
        compact.append(
            {
                "id": str(r["id"]),
                "name_en": r.get("name_en"),
                "name_zh": r.get("name_zh"),
                "muscle": r.get("muscle"),
                "sub_region": r.get("sub_region"),
                "target": r.get("target"),
                "equipment": r.get("equipment"),
                "instructions_en": (r.get("instructions_en") or [])[:5],
            }
        )
    user = "请清洗以下动作列表，按要求返回 JSON 数组：\n" + json.dumps(
        compact, ensure_ascii=False
    )
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": LLM_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]

    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # tolerate prose around array
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("LLM did not return a list")
    return data


def stage2_llm(
    rows: list[dict[str, Any]],
    *,
    limit: int | None = None,
    batch_size: int = 8,
) -> list[dict[str, Any]]:
    by_id = {str(r["id"]): r for r in rows}
    cores = [r for r in rows if r.get("coach_core") and r.get("is_valid_exercise")]
    cores.sort(key=lambda r: (_en(r) not in COACH_CORE_BY_EN, _en(r)))
    if limit is not None:
        cores = cores[:limit]

    cache = _load_cache()
    todo = [r for r in cores if str(r["id"]) not in cache]
    print(
        f"[stage2] coach_core={len(cores)} cached={len(cores)-len(todo)} todo={len(todo)}",
        flush=True,
    )

    for i in range(0, len(todo), batch_size):
        batch = todo[i : i + batch_size]
        ids = [str(r["id"]) for r in batch]
        print(f"[stage2] batch {i // batch_size + 1}/{ (len(todo) + batch_size - 1)//batch_size }: {ids}", flush=True)
        for attempt in range(3):
            try:
                results = _call_llm(batch)
                for item in results:
                    rid = str(item.get("id") or "")
                    if rid:
                        cache[rid] = item
                _save_cache(cache)
                print(f"  ok +{len(results)} cache={len(cache)}", flush=True)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  attempt {attempt+1} failed: {exc}", flush=True)
                time.sleep(2 + attempt * 2)
        else:
            print(f"  SKIP batch {ids}", flush=True)
        time.sleep(0.4)
    print("[stage2] llm loop done", flush=True)

    for rid, item in cache.items():
        row = by_id.get(str(rid))
        if not row:
            continue
        if item.get("name_zh"):
            row["name_zh"] = str(item["name_zh"]).strip()
        aliases = item.get("aliases") or []
        if isinstance(aliases, list):
            row["aliases"] = [str(a).strip() for a in aliases if str(a).strip()][:6]
        if item.get("sub_region"):
            row["sub_region"] = str(item["sub_region"]).strip()
        inst = item.get("instructions_zh") or []
        if isinstance(inst, list) and len(inst) >= 3:
            row["instructions_zh"] = [str(x).strip() for x in inst[:4] if str(x).strip()]
        cues = item.get("cues_zh") or []
        if isinstance(cues, list):
            row["cues_zh"] = [str(x).strip() for x in cues[:3] if str(x).strip()]
        mistakes = item.get("common_mistakes_zh") or []
        if isinstance(mistakes, list):
            row["common_mistakes_zh"] = [str(x).strip() for x in mistakes[:3] if str(x).strip()]
        if isinstance(item.get("joint_stress"), dict):
            row["joint_stress"] = item["joint_stress"]
        row["enrich_stage"] = 2
        _clamp_enum(row)

    return rows


def write_report(rows: list[dict[str, Any]], path: Path) -> None:
    total = len(rows)
    valid = sum(1 for r in rows if r.get("is_valid_exercise"))
    core = [r for r in rows if r.get("coach_core")]
    stage2 = sum(1 for r in core if r.get("enrich_stage") == 2)
    with_alias = sum(1 for r in core if r.get("aliases"))
    with_cues = sum(1 for r in core if r.get("cues_zh"))
    with_inst = sum(1 for r in rows if r.get("instructions_zh"))
    with_img = sum(1 for r in rows if r.get("image_start"))

    muscle_c = Counter(r.get("muscle") for r in rows)
    sub_c = Counter(r.get("sub_region") for r in rows)
    pattern_c = Counter(r.get("movement_pattern") for r in rows)
    core_muscle = Counter(r.get("muscle") for r in core)

    # enum violations
    bad_muscle = [r["id"] for r in rows if r.get("muscle") not in MUSCLE_WHITELIST]
    bad_sub = [r["id"] for r in rows if r.get("sub_region") not in SUB_REGION_WHITELIST]
    bad_pat = [r["id"] for r in rows if r.get("movement_pattern") not in PATTERN_WHITELIST]

    lines = [
        "# 动作库清洗报告",
        "",
        f"- 总条数：{total}",
        f"- 有效动作 `is_valid_exercise`：{valid}",
        f"- 主力动作 `coach_core`：{len(core)}",
        f"- 主力已 LLM 精洗（stage2）：{stage2}",
        f"- 主力已有 aliases：{with_alias}",
        f"- 主力已有 cues_zh：{with_cues}",
        f"- 全库有 instructions_zh：{with_inst}",
        f"- 有 image_start：{with_img}",
        "",
        "## 枚举校验",
        f"- muscle 违规：{len(bad_muscle)}",
        f"- sub_region 违规：{len(bad_sub)}",
        f"- movement_pattern 违规：{len(bad_pat)}",
        "",
        "## 主部位分布（全库）",
    ]
    for k, v in muscle_c.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 主力动作主部位分布"]
    for k, v in core_muscle.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 细分靶区 Top 30"]
    for k, v in sub_c.most_common(30):
        lines.append(f"- {k}: {v}")
    lines += ["", "## 动作模式分布"]
    for k, v in pattern_c.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 主力动作样例（前 40）"]
    for r in sorted(core, key=lambda x: str(x.get("name_zh") or ""))[:40]:
        lines.append(
            f"- [{r['id']}] {r.get('name_zh')} / {r.get('name_en')} · "
            f"{r.get('muscle')}/{r.get('sub_region')} · aliases={r.get('aliases')}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[report] wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="run stage2 LLM on coach_core")
    parser.add_argument("--limit", type=int, default=None, help="limit stage2 rows")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--from-out", action="store_true", help="load existing enriched as base")
    args = parser.parse_args()

    if args.report_only:
        if not OUT.exists():
            raise SystemExit(f"missing {OUT}")
        rows = json.loads(OUT.read_text(encoding="utf-8"))
        write_report(rows, REPORT)
        return

    if args.from_out and OUT.exists():
        rows = json.loads(OUT.read_text(encoding="utf-8"))
        print(f"[load] existing enriched {len(rows)}")
    else:
        raw = json.loads(SRC.read_text(encoding="utf-8"))
        print(f"[stage1] source={len(raw)}")
        rows = stage1_enrich(raw)
        for r in rows:
            _clamp_enum(r)
        print(f"[stage1] done valid={sum(1 for r in rows if r.get('is_valid_exercise'))} "
              f"core={sum(1 for r in rows if r.get('coach_core'))}")

    if args.llm:
        rows = stage2_llm(rows, limit=args.limit, batch_size=args.batch_size)

    # final clamp
    for r in rows:
        _clamp_enum(r)

    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[write] {OUT} ({OUT.stat().st_size} bytes)")
    write_report(rows, REPORT)

    # also copy report into plan docs
    plan_report = Path(r"D:\桌面Dowload\gym-admin-plan\docs\03-清洗验收报告.md")
    if plan_report.parent.exists():
        plan_report.write_text(REPORT.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[copy] {plan_report}")


if __name__ == "__main__":
    main()
