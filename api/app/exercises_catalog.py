"""Static exercise catalog for swap / injury soft filters (Phase 1)."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict
from app.taxonomy import canonicalize_exercise

LoadLevel = Literal["low", "medium", "high"]


class ExerciseDetail(TypedDict):
    name: str
    muscle: str  # UI 默认展示；本堂用法由模型从 roles 里选
    category: str  # 器械 | 自由重量 | 绳索 | 自重
    tips: str
    axial_load: LoadLevel  # 脊柱垂直轴向压迫
    knee_stress: LoadLevel  # 膝关节剪切与高压
    shoulder_stress: LoadLevel  # 肩关节过头与撞击压力
    roles: NotRequired[list[str]]  # 这个动作能顶的用途；模型按用户这句话选


# Detailed categorized catalog with Biomechanical Profiles
EXERCISES_DATABASE: list[ExerciseDetail] = [
    # ---------- 胸部 ----------
    {"name": "哑铃卧推", "muscle": "胸", "category": "自由重量", "tips": "哑铃活动度大，对胸大肌拉伸更深", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "杠铃卧推", "muscle": "胸", "category": "自由重量", "tips": "黄金复合推力动作，上重量首选", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "上斜哑铃推", "muscle": "胸", "category": "自由重量", "tips": "强化胸肌上束，塑造饱满锁骨线", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "上斜杠铃卧推", "muscle": "胸", "category": "自由重量", "tips": "重负荷上胸强化动作", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "器械夹胸", "muscle": "胸", "category": "器械", "tips": "坐姿固定轨迹，安全刺激中缝收缩", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "器械推胸机", "muscle": "胸", "category": "器械", "tips": "固定轨迹新手友好，不易耸肩借力", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "史密斯卧推", "muscle": "胸", "category": "器械", "tips": "轨道受限稳定，适合大重量力竭", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "绳索夹胸", "muscle": "胸", "category": "绳索", "tips": "全程持续张力，胸大肌泵感极强", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "高位绳索夹胸", "muscle": "胸", "category": "绳索", "tips": "重点强化下胸轮廓与收缩", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "低位绳索飞鸟", "muscle": "胸", "category": "绳索", "tips": "自下而上夹胸，深度刺激上胸", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "双杠臂屈伸", "muscle": "胸", "category": "自重", "tips": "上半身深蹲，躯干前倾主练下胸", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "high"},
    {"name": "俯卧撑", "muscle": "胸", "category": "自重", "tips": "经典居家胸肌训练，核心同时收紧", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "哑铃飞鸟", "muscle": "胸", "category": "自由重量", "tips": "微屈手肘，专注胸肌顶峰收缩", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},

    # ---------- 背部 ----------
    {"name": "高位下拉", "muscle": "背", "category": "器械", "tips": "背阔肌宽度首选，沉肩后拉", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "反手高位下拉", "muscle": "背", "category": "器械", "tips": "下背阔肌更强受力，带微屈手臂二头", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "窄距高位下拉", "muscle": "背", "category": "器械", "tips": "采用V柄把手，深度刺激背阔中下部", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "坐姿绳索划船", "muscle": "背", "category": "绳索", "tips": "沉肩收核心，双肘贴身体后拉强化背厚", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "单臂哑铃划船", "muscle": "背", "category": "自由重量", "tips": "单侧独立发力，纠正左右肌力不平衡", "axial_load": "medium", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "引体向上", "muscle": "背", "category": "自重", "tips": "上肢拉力之王，自重背阔发展首选", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "反手引体向上", "muscle": "背", "category": "自重", "tips": "兼顾背阔肌与肱二头肌的拉力复合", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "杠铃划船", "muscle": "背", "category": "自由重量", "tips": "重负荷练背厚度，俯身收紧核心", "axial_load": "high", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "T杆划船", "muscle": "背", "category": "器械", "tips": "轨迹固定稳定，背部中缝与厚度利器", "axial_load": "medium", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "面拉", "muscle": "背", "category": "绳索", "tips": "强化上背与肩袖后束，改善圆肩驼背", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "直臂下压", "muscle": "背", "category": "绳索", "tips": "孤立背阔肌下压，手臂不借力的单关节动作", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "器械划船机", "muscle": "背", "category": "器械", "tips": "有胸部支撑垫，安全减轻腰椎压力", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "杠铃硬拉", "muscle": "背", "category": "自由重量", "tips": "后侧链复合动作；全力硬拉练后链，半程/锁住可偏背厚", "axial_load": "high", "knee_stress": "medium", "shoulder_stress": "low"},

    # ---------- 肩部 ----------
    {"name": "哑铃侧平举", "muscle": "肩", "category": "自由重量", "tips": "外展肩膀，打造南瓜肩中束宽度", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "坐姿推举", "muscle": "肩", "category": "自由重量", "tips": "三角肌前束与全肩复合推力动作", "axial_load": "medium", "knee_stress": "low", "shoulder_stress": "high"},
    {"name": "绳索侧平举", "muscle": "肩", "category": "绳索", "tips": "底部无死点，全程保持中束张力", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "阿诺德推举", "muscle": "肩", "category": "自由重量", "tips": "带旋转轨迹，全面刺激前束与中束", "axial_load": "medium", "knee_stress": "low", "shoulder_stress": "high"},
    {"name": "器械推肩机", "muscle": "肩", "category": "器械", "tips": "坐姿固定推举，不易借力耸肩", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "俯身飞鸟", "muscle": "肩", "category": "自由重量", "tips": "针对后束孤立刺激，强化肩关节后侧", "axial_load": "medium", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "绳索面拉", "muscle": "肩", "category": "绳索", "tips": "强化后束与肩袖，打造饱满后肩", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "蝴蝶机反向飞鸟", "muscle": "肩", "category": "器械", "tips": "胸贴靠背，稳定孤立三角肌后束", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},

    # ---------- 腿部 ----------
    {"name": "腿举", "muscle": "腿", "category": "器械", "tips": "倒蹬机大负荷练股四与臀大肌，腰部压力小", "axial_load": "low", "knee_stress": "medium", "shoulder_stress": "low"},
    {"name": "腿屈伸", "muscle": "腿", "category": "器械", "tips": "单关节孤立股四头肌，雕刻大腿前侧细节", "axial_load": "low", "knee_stress": "high", "shoulder_stress": "low"},
    {"name": "坐姿腿弯举", "muscle": "腿", "category": "器械", "tips": "强化大腿后侧腘绳肌，提升膝关节稳定性", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "哈克深蹲", "muscle": "腿", "category": "器械", "tips": "靠背支撑，比自由深蹲更安全聚焦股四", "axial_load": "medium", "knee_stress": "high", "shoulder_stress": "low"},
    {"name": "臀桥", "muscle": "腿", "category": "自重", "tips": "激活臀大肌，改善骨盆前倾", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "罗马尼亚硬拉", "muscle": "腿", "category": "自由重量", "tips": "微屈膝屈髋，深度拉伸腘绳肌与臀部；直腿变式更偏股二", "axial_load": "high", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "保加利亚分腿蹲", "muscle": "腿", "category": "自由重量", "tips": "单腿自重或负重，极致激活臀腿", "axial_load": "medium", "knee_stress": "high", "shoulder_stress": "low"},
    {"name": "杠铃深蹲", "muscle": "腿", "category": "自由重量", "tips": "下肢动作之王，全身力量核心基础", "axial_load": "high", "knee_stress": "high", "shoulder_stress": "low"},

    # ---------- 手臂 ----------
    {"name": "哑铃弯举", "muscle": "臂", "category": "自由重量", "tips": "经典二头肌孤立动作，顶峰旋转", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "绳索下压", "muscle": "臂", "category": "绳索", "tips": "三头肌经典下压，肘关节紧贴身体两侧", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "锤式弯举", "muscle": "臂", "category": "自由重量", "tips": "掌心相对，强化肱肌与前臂粗细", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "过头臂屈伸", "muscle": "臂", "category": "自由重量", "tips": "充分拉伸三头肌长头，打造饱满大臂", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "medium"},
    {"name": "杠铃弯举", "muscle": "臂", "category": "自由重量", "tips": "大重量二头肌肌肥大首选", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},

    # ---------- 核心与全身 ----------
    {"name": "平板支撑", "muscle": "核心", "category": "自重", "tips": "静力核心稳定，腹部臀部同时绷紧", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "卷腹", "muscle": "核心", "category": "自重", "tips": "下背贴地，下巴微收，感受腹直肌卷曲", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "死虫", "muscle": "核心", "category": "自重", "tips": "对角线手臂双腿伸展，保护腰椎的核心激活", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "鸟狗式", "muscle": "核心", "category": "自重", "tips": "四点支撑对侧手脚伸展，后侧链稳定训练", "axial_load": "low", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "哑铃农夫走", "muscle": "全身", "category": "自由重量", "tips": "手握重物保持躯干稳定行走，核心握力双收", "axial_load": "medium", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "壶铃摇摆", "muscle": "全身", "category": "自由重量", "tips": "屈髋爆发力训练，心肺与臀大肌高效燃脂", "axial_load": "medium", "knee_stress": "low", "shoulder_stress": "low"},
    {"name": "波比跳", "muscle": "全身", "category": "自重", "tips": "全身高强度燃脂动作，快速拉升心率", "axial_load": "low", "knee_stress": "high", "shoulder_stress": "low"},
]

# 复合动作：目录只记它能顶哪些用途，本堂选哪一面交给模型
_ROLE_OVERRIDES: dict[str, list[str]] = {
    "杠铃硬拉": ["背", "腿", "全身"],
    "罗马尼亚硬拉": ["腿", "背"],
    "双杠臂屈伸": ["胸", "臂"],
    "反手引体向上": ["背", "臂"],
    "反手高位下拉": ["背", "臂"],
    "俯卧撑": ["胸", "核心"],
    "壶铃摇摆": ["全身", "腿"],
    "哑铃农夫走": ["全身", "核心"],
    "鸟狗式": ["核心", "背"],
}
for _item in EXERCISES_DATABASE:
    _item["roles"] = list(dict.fromkeys(_ROLE_OVERRIDES.get(_item["name"], [_item["muscle"]])))

# Quick map by canonical exercise name
EXERCISE_BY_NAME: dict[str, ExerciseDetail] = {
    canonicalize_exercise(it["name"]): it for it in EXERCISES_DATABASE
}

# 口语简称 → 目录里的规范名。全名优先匹配，避免「罗马尼亚硬拉」被收成「杠铃硬拉」。
SPOKEN_EXERCISE_ALIASES: list[tuple[str, str]] = [
    ("深蹲", "杠铃深蹲"),
    ("直腿硬拉", "罗马尼亚硬拉"),
    ("罗马尼亚硬拉", "罗马尼亚硬拉"),
    ("半程硬拉", "杠铃硬拉"),
    ("硬拉", "杠铃硬拉"),
    ("卧推", "杠铃卧推"),
    ("引体", "引体向上"),
    ("推举", "坐姿推举"),
    ("侧平举", "哑铃侧平举"),
    ("弯举", "哑铃弯举"),
    ("臂屈伸", "双杠臂屈伸"),
    ("平板", "平板支撑"),
    ("农夫走", "哑铃农夫走"),
]


def roles_of(name: str | None = None, detail: ExerciseDetail | None = None) -> list[str]:
    """这个动作能服务哪些部位。没有多用途时就是默认展示部位。"""
    row = detail
    if row is None and name:
        row = EXERCISE_BY_NAME.get(canonicalize_exercise(name))
    if not row:
        return []
    roles = row.get("roles")
    if roles:
        return list(roles)
    return [row["muscle"]]


def find_exercises_in_text(text: str) -> list[str]:
    """从口语里找出点名的动作。长名称先占位，简称只在没被全名覆盖时生效。"""
    needles = [(it["name"], it["name"]) for it in EXERCISES_DATABASE]
    needles.extend(SPOKEN_EXERCISE_ALIASES)
    needles.sort(key=lambda pair: len(pair[0]), reverse=True)
    occupied = [False] * len(text)
    found: list[str] = []
    for needle, canonical in needles:
        start = 0
        while True:
            index = text.find(needle, start)
            if index < 0:
                break
            end = index + len(needle)
            if not any(occupied[index:end]):
                for pos in range(index, end):
                    occupied[pos] = True
                if canonical not in found:
                    found.append(canonical)
            start = index + 1
    return found


# Quick lookup by muscle / role
BY_MUSCLE: dict[str, list[str]] = {}
for _item in EXERCISES_DATABASE:
    for role in roles_of(detail=_item):
        BY_MUSCLE.setdefault(role, [])
        if _item["name"] not in BY_MUSCLE[role]:
            BY_MUSCLE[role].append(_item["name"])

# Fallback injury keywords (for custom or unknown exercises - Fail Closed)
INJURY_BANNED_FALLBACK: dict[str, list[str]] = {
    "腰": ["硬拉", "早安", "杠铃深蹲", "山羊挺身", "负重体前屈"],
    "腰椎": ["硬拉", "早安", "杠铃深蹲", "山羊挺身"],
    "膝盖": ["深蹲", "箭步", "弓步", "跳箱", "腿屈伸", "分腿蹲"],
    "膝": ["深蹲", "箭步", "弓步", "跳箱", "腿屈伸", "分腿蹲"],
    "肩": ["过头推举", "颈后", "直立划船", "杠铃推举", "双杠臂屈伸"],
    "手腕": ["杠铃卧推", "杠铃弯举", "正握"],
    "肘": ["窄距卧推", "臂屈伸", "法式推举"],
}


def alternatives(muscle: str, exclude: str | None = None, injuries: list[str] | None = None) -> list[str]:
    details = alternatives_rich(muscle, exclude=exclude, injuries=injuries)
    return [d["name"] for d in details]


def alternatives_rich(
    muscle: str,
    exclude: str | None = None,
    injuries: list[str] | None = None,
) -> list[ExerciseDetail]:
    """按用途筛替代：能顶这个部位的都进来，不限目录默认那一格。"""
    ex = canonicalize_exercise(exclude) if exclude else None
    out: list[ExerciseDetail] = []
    for item in EXERCISES_DATABASE:
        roles = roles_of(detail=item)
        if muscle != "全身" and muscle not in roles:
            continue
        name = canonicalize_exercise(item["name"])
        if ex and name == ex:
            continue
        if injuries and is_banned_for_injuries(name, injuries):
            continue
        out.append(item)
    return out


def is_banned_for_injuries(title: str, injuries: list[str]) -> bool:
    """Biomechanical rules + Fallback keyword safety filter (Fail-Closed)."""
    t = canonicalize_exercise(title)
    detail = EXERCISE_BY_NAME.get(t)

    for inj in injuries:
        if not inj:
            continue
        inj_clean = inj.strip()

        # 1. 生物力学受力维度判断 (Biomechanical Profile)
        if any(w in inj_clean for w in ("腰", "下背", "脊椎")):
            if detail and detail.get("axial_load") == "high":
                return True
        if any(w in inj_clean for w in ("膝", "髌骨", "半月板")):
            if detail and detail.get("knee_stress") == "high":
                return True
        if any(w in inj_clean for w in ("肩", "肩袖")):
            if detail and detail.get("shoulder_stress") == "high":
                return True

        # 2. 备用关键字过滤 (Fail-Closed 兜底未知动作)
        for key, banned in INJURY_BANNED_FALLBACK.items():
            if key in inj_clean:
                if any(b in t for b in banned):
                    return True
        if inj_clean in t:
            return True

    return False


def suggest_weight_from_stats(
    last_weight: float | None,
    experience: str,
    last_feeling: str | None = None,
    last_outcome: str | None = None,
) -> float | None:
    if last_weight is None:
        return None
    # 1. 手动体感优先
    if last_feeling == "力竭":
        return last_weight
    if last_feeling == "轻松":
        bump = 2.5 if experience in ("进阶", "老炮") else 1.25
        return round(last_weight + bump, 1)
    if last_feeling == "合适":
        return last_weight

    # 2. 客观组数/次数/重量偏差
    if last_outcome in ("次数未达标", "没做完", "降重完成"):
        return last_weight
    if last_outcome == "超额完成":
        bump = 2.5 if experience in ("进阶", "老炮") else 1.25
        return round(last_weight + bump, 1)
    if last_outcome in ("加重完成", "达标"):
        return last_weight
    return last_weight
