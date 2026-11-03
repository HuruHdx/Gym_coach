"""Map openGym fields onto gym-coach muscle / modality / gear / roles."""

from __future__ import annotations

from typing import Any, Literal

Modality = Literal["抗阻", "有氧", "HIIT", "灵活性"]
Gear = Literal["器械", "自由重量", "绳索", "自重"]

# Preferred Chinese display names (coach UX) → openGym name_en (exact preferred)
COACH_CORE_BY_EN: dict[str, str] = {
    "dumbbell bench press": "哑铃卧推",
    "barbell bench press": "杠铃卧推",
    "dumbbell incline bench press": "上斜哑铃推",
    "barbell incline bench press": "上斜杠铃卧推",
    "push-up": "俯卧撑",
    "pull-up": "引体向上",
    "chin-up": "反手引体向上",
    "barbell deadlift": "杠铃硬拉",
    "barbell romanian deadlift": "罗马尼亚硬拉",
    "barbell squat": "杠铃深蹲",
    "dumbbell lateral raise": "哑铃侧平举",
    "cable seated row": "坐姿绳索划船",
    "barbell bent over row": "杠铃划船",
    "barbell curl": "杠铃弯举",
    "cable pushdown": "绳索下压",
    "dumbbell seated shoulder press": "坐姿推举",
    "dumbbell arnold press": "阿诺德推举",
    "mountain climber": "登山跑",
    "burpee": "波比跳",
    "jumping jack": "开合跳",
    "kettlebell swing": "壶铃摇摆",
    "farmers walk": "农夫走",
    "hip thrusts": "臀桥",
    "bird dog": "鸟狗式",
    "dead bug": "死虫",
    "cat cow stretch": "猫牛式",
}

BODY_PART_TO_MUSCLE: dict[str, str] = {
    "chest": "胸",
    "back": "背",
    "shoulders": "肩",
    "upper arms": "臂",
    "lower arms": "臂",
    "upper legs": "腿",
    "lower legs": "腿",
    "waist": "核心",
    "neck": "肩",
    "cardio": "全身",
    "full body": "全身",
}

TARGET_TO_MUSCLE: dict[str, str] = {
    "pectorals": "胸",
    "lats": "背",
    "upper back": "背",
    "traps": "背",
    "spine": "背",
    "delts": "肩",
    "levator scapulae": "肩",
    "biceps": "臂",
    "triceps": "臂",
    "forearms": "臂",
    "quads": "腿",
    "hamstrings": "腿",
    "glutes": "腿",
    "calves": "腿",
    "abductors": "腿",
    "adductors": "腿",
    "abs": "核心",
    "serratus anterior": "核心",
    "cardiovascular system": "全身",
}

CATEGORY_TO_MODALITY: dict[str, Modality] = {
    "strength": "抗阻",
    "olympic": "抗阻",
    "calisthenics": "抗阻",
    "isometric": "抗阻",
    "rehab": "抗阻",
    "cardio": "有氧",
    "plyometrics": "HIIT",
    "combat": "HIIT",
    "stretching": "灵活性",
    "mobility": "灵活性",
    "yoga": "灵活性",
    "pilates": "灵活性",
}

EQUIPMENT_TO_GEAR: dict[str, Gear] = {
    "body weight": "自重",
    "assisted": "自重",
    "dumbbell": "自由重量",
    "barbell": "自由重量",
    "ez barbell": "自由重量",
    "kettlebell": "自由重量",
    "olympic barbell": "自由重量",
    "trap bar": "自由重量",
    "weight plate": "自由重量",
    "weighted": "自由重量",
    "medicine ball": "自由重量",
    "cable": "绳索",
    "rope": "绳索",
    "resistance band": "绳索",
    "band": "绳索",
    "leverage machine": "器械",
    "smith machine": "器械",
    "sled machine": "器械",
    "stationary bike": "器械",
    "elliptical machine": "器械",
    "stepmill machine": "器械",
    "skierg machine": "器械",
    "bosu ball": "器械",
    "stability ball": "器械",
    "roller": "器械",
    "wheel roller": "器械",
    "suspension trainer": "器械",
    "tire": "器械",
    "hammer": "器械",
    "landmine": "器械",
}

# Keyword soft-ban for injury-aware retrieval (name_zh + name_en)
INJURY_NAME_KEYWORDS: dict[str, list[str]] = {
    "腰": ["硬拉", "deadlift", "早安", "good morning", "山羊", "hyperextension", "负重体前屈"],
    "腰椎": ["硬拉", "deadlift", "早安", "good morning", "山羊", "hyperextension"],
    "下背": ["硬拉", "deadlift", "早安", "good morning"],
    "脊椎": ["硬拉", "deadlift", "早安", "good morning"],
    "膝盖": ["深蹲", "squat", "箭步", "弓步", "lunge", "跳", "jump", "腿屈伸", "leg extension", "分腿蹲", "split squat"],
    "膝": ["深蹲", "squat", "箭步", "弓步", "lunge", "跳", "jump", "腿屈伸", "leg extension", "分腿蹲", "split squat"],
    "髌骨": ["深蹲", "squat", "lunge", "jump", "腿屈伸"],
    "半月板": ["深蹲", "squat", "lunge", "jump"],
    "肩": ["过头", "overhead", "颈后", "behind the neck", "直立划船", "upright row", "双杠", "dip"],
    "肩袖": ["过头", "overhead", "颈后", "upright row"],
    "手腕": ["杠铃卧推", "barbell bench", "杠铃弯举", "barbell curl"],
    "肘": ["窄距卧推", "close-grip bench", "臂屈伸", "dip", "法式推举", "skull crusher"],
}

ROLE_OVERRIDES_BY_EN: dict[str, list[str]] = {
    "barbell deadlift": ["背", "腿", "全身"],
    "barbell romanian deadlift": ["腿", "背"],
    "push-up": ["胸", "核心"],
    "chin-up": ["背", "臂"],
    "mountain climber": ["核心", "全身"],
    "kettlebell swing": ["全身", "腿"],
    "farmers walk": ["全身", "核心"],
    "bird dog": ["核心", "背"],
    "cat cow stretch": ["背", "核心"],
    "burpee": ["全身"],
    "jump squat": ["腿", "全身"],
}

MODALITY_OVERRIDE_BY_EN: dict[str, Modality] = {
    "mountain climber": "HIIT",
    "burpee": "HIIT",
    "jumping jack": "HIIT",
    "jump squat": "HIIT",
    "high knees butt kicks": "HIIT",
    "walk (high knees)": "HIIT",
    "battling ropes": "HIIT",
}


def map_muscle(body_part: str | None, target: str | None) -> str:
    t = (target or "").strip().lower()
    if t in TARGET_TO_MUSCLE:
        return TARGET_TO_MUSCLE[t]
    bp = (body_part or "").strip().lower()
    return BODY_PART_TO_MUSCLE.get(bp, "全身")


def map_modality(category: str | None) -> Modality:
    return CATEGORY_TO_MODALITY.get((category or "").strip().lower(), "抗阻")


def map_gear(equipment: str | None) -> Gear:
    eq = (equipment or "").strip().lower()
    if eq in EQUIPMENT_TO_GEAR:
        return EQUIPMENT_TO_GEAR[eq]
    if "cable" in eq or "band" in eq:
        return "绳索"
    if "machine" in eq or "smith" in eq or "lever" in eq:
        return "器械"
    if any(k in eq for k in ("dumbbell", "barbell", "kettle", "plate", "ez ")):
        return "自由重量"
    if "body" in eq or eq in ("", "none"):
        return "自重"
    return "器械"


def map_roles(name_en: str | None, muscle: str) -> list[str]:
    en = (name_en or "").strip().lower()
    if en in ROLE_OVERRIDES_BY_EN:
        return list(ROLE_OVERRIDES_BY_EN[en])
    # light heuristics
    roles = [muscle]
    if "deadlift" in en:
        roles = ["背", "腿", "全身"]
    elif "romanian" in en:
        roles = ["腿", "背"]
    elif "chin-up" in en or "underhand" in en and "pull" in en:
        roles = ["背", "臂"]
    elif "dip" in en:
        roles = ["胸", "臂"]
    elif "push-up" in en or "pushup" in en:
        roles = ["胸", "核心"]
    return list(dict.fromkeys(roles))


def injury_keywords_for(injuries: list[str] | None) -> list[str]:
    if not injuries:
        return []
    out: list[str] = []
    for inj in injuries:
        if not inj:
            continue
        clean = inj.strip()
        for key, words in INJURY_NAME_KEYWORDS.items():
            if key in clean:
                out.extend(words)
    return list(dict.fromkeys(out))


def matches_injury_keywords(name_zh: str, name_en: str, keywords: list[str]) -> bool:
    if not keywords:
        return False
    blob = f"{name_zh} {name_en}".lower()
    return any(k.lower() in blob for k in keywords)


def enrich_raw(row: dict[str, Any]) -> dict[str, Any]:
    """Add derived coach fields onto an openGym JSON row (non-destructive copy)."""
    name_en = row.get("name_en") or ""
    name_zh = (row.get("name_zh") or name_en or "").strip()
    muscle = map_muscle(row.get("body_part"), row.get("target"))
    en_key = name_en.strip().lower()
    modality = MODALITY_OVERRIDE_BY_EN.get(en_key) or map_modality(row.get("category"))
    gear = map_gear(row.get("equipment"))
    roles = map_roles(name_en, muscle)
    preferred = COACH_CORE_BY_EN.get(en_key)
    coach_core = preferred is not None
    display = preferred or name_zh
    return {
        **row,
        "name_zh": name_zh,
        "muscle": muscle,
        "modality": modality,
        "gear": gear,
        "roles": roles,
        "coach_core": coach_core,
        "display_name": display,
    }
