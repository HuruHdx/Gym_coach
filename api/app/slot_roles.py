"""计划槽位角色：只信 taxonomy 枚举字段，不靠动作名中文写死。

权威字段（后台填准后，配课/换动作代码不用再改）：
- ``Exercise.slot_roles``：main / assist / isolation / warmup（人工或启动回填）
- ``Exercise.movement_pattern``：受控枚举，见下方集合
- ``Exercise.muscle``：胸/背/肩/腿/臂/核心/全身
- ``PlanExercise.target_muscle``：单行目标肌群（框架配课按此抽，勿与板块 muscles 混池）

禁止：在配课、换动作、检索热路径用「动作名包含某某」维护名单。
名字启发只允许出现在后台一次性「猜分类」工具（``admin_editor._guess_taxonomy``），
用途是把脏数据填进上述字段，而不是长期当运行时规则。
"""

from __future__ import annotations

from typing import Any

PLAN_SLOT_ROLES = ("main", "assist", "isolation", "warmup")

# —— 以下集合是产品受控枚举，不是动作名清单 ——
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
_CORE_PATTERN = "核心卷曲/稳定"


def is_core_movement(
    *,
    movement_pattern: str | None = None,
    muscle: str | None = None,
    name: str | None = None,  # 保留签名兼容旧调用；**忽略**，勿再靠名字判核心
) -> bool:
    """核心动作：只看主肌群 / 动作模式枚举。"""
    del name  # 显式丢弃，防止后人再写名字分支
    if (muscle or "").strip() == "核心":
        return True
    return (movement_pattern or "").strip() == _CORE_PATTERN


def infer_slot_roles(
    *,
    movement_pattern: str | None = None,
    gear: str | None = None,
    modality: str | None = None,
    coach_core: bool = False,
    name: str | None = None,  # 兼容旧调用；**忽略**
    muscle: str | None = None,
) -> list[str]:
    """仅在 ``slot_roles`` 为空时预填；有人工值的行不会被覆盖（见 db._backfill_slot_roles）。"""
    del name
    pattern = (movement_pattern or "").strip()
    modality_s = (modality or "").strip()
    gear_s = (gear or "").strip()
    muscle_s = (muscle or "").strip()

    if modality_s == "灵活性" or pattern in _WARMUP_PATTERNS:
        return ["warmup"]
    if muscle_s == "核心" or pattern == _CORE_PATTERN:
        return ["isolation"]
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
