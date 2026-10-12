"""从一次训练的计划 vs 实际（组数、次数、重量），推出客观动作表现。

不依赖主观标签，由客观数据偏差（Delta）确定性判定。
"""

from __future__ import annotations

import re
from typing import Protocol

WEIGHT_STEP = 2.5


class SetLike(Protocol):
    completed: bool
    set_index: int
    target_weight: float | None
    actual_weight: float | None
    target_reps: str | None
    actual_reps: int | None
    feeling: str | None


def parse_target_reps_bounds(target_reps: str | None) -> tuple[int | None, int | None]:
    """解析目标次数范围。

    例如：
    - "8-10次" / "8-10" / "8~10" -> (8, 10)
    - "12次" / "12" -> (12, 12)
    - "AMRAP" / "40s" / None -> (None, None)
    """
    if not target_reps:
        return None, None
    s = target_reps.strip().lower().replace("次", "").replace("个", "")
    m_range = re.search(r"(\d+)\s*[-~至到]\s*(\d+)", s)
    if m_range:
        return int(m_range.group(1)), int(m_range.group(2))
    m_single = re.search(r"(\d+)", s)
    if m_single:
        val = int(m_single.group(1))
        return val, val
    return None, None


def reference_set(sets: list[SetLike]) -> SetLike | None:
    """下次参考用的那一组：已勾选里实际重量最高的一组。没有重量则取最后一组。"""
    done = [s for s in sets if s.completed]
    if not done:
        return None
    weighted = [s for s in done if s.actual_weight is not None]
    if weighted:
        return max(weighted, key=lambda s: (s.actual_weight or 0, s.set_index))
    return max(done, key=lambda s: s.set_index)


def judge_performance(sets: list[SetLike]) -> str | None:
    """先组数，再重量，再次数。

    - None: 一组都没勾，这次跳过
    - 没做完: 勾选组数少于计划
    - 加重完成 / 降重完成: 组数够了，参考组重量差达到 2.5kg。重量优先于次数。
    - 次数未达标 / 超额完成: 重量没有明显升降时，再看次数是否偏离目标区间 2 次。
    - 达标: 组数、重量、次数都在计划附近
    """
    if not sets:
        return None
    done = [s for s in sets if s.completed]
    if not done:
        return None
    if len(done) < len(sets):
        return "没做完"

    ref = reference_set(done)
    if ref is not None and ref.target_weight is not None and ref.actual_weight is not None:
        delta = ref.actual_weight - ref.target_weight
        if delta >= WEIGHT_STEP:
            return "加重完成"
        if delta <= -WEIGHT_STEP:
            return "降重完成"

    reps_deficits = 0
    reps_surplus = 0
    has_reps_target = False
    for s in done:
        min_r, max_r = parse_target_reps_bounds(s.target_reps)
        if min_r is None or s.actual_reps is None:
            continue
        has_reps_target = True
        if s.actual_reps <= min_r - 2:
            reps_deficits += 1
        elif max_r is not None and s.actual_reps >= max_r + 2:
            reps_surplus += 1

    if has_reps_target and reps_deficits > 0:
        return "次数未达标"
    if has_reps_target and reps_surplus >= len(done) // 2 + 1:
        return "超额完成"
    return "达标"


def session_volume(sets: list[SetLike]) -> float:
    """已勾选组的容量：实际重量 × 实际次数。没记重量或次数的组不计入。"""
    total = 0.0
    for s in sets:
        if not s.completed or s.actual_weight is None or s.actual_reps is None:
            continue
        total += float(s.actual_weight) * int(s.actual_reps)
    return round(total, 1)


def judge_session(outcomes: list[str]) -> str:
    """一场训练的总状态。看所有做过的动作，不看被跳过的。"""
    done = [o for o in outcomes if o]
    if not done:
        return "未记录"
    if all(o == "没做完" for o in done):
        return "未完成"
    up = sum(1 for o in done if o == "加重完成")
    hard = sum(1 for o in done if o in ("没做完", "次数未达标", "降重完成"))
    if up and hard <= len(done) / 2:
        return "有突破"
    if hard > len(done) / 2:
        return "偏吃力"
    return "完成"


def build_session_summary(
    split_label: str | None,
    groups: list[tuple[str, str, list]],
    minutes: int | None = None,
) -> str:
    """给人看的复盘。容量数字留给以后的统计，不写进这段话。"""
    named = [(name, outcome, rows) for name, outcome, rows in groups if outcome]
    if not named:
        return "这次没有勾选完成的组。"

    muscles: list[str] = []
    for _, _, rows in named:
        for row in rows:
            muscle = getattr(row, "muscle", None)
            if muscle and muscle not in muscles:
                muscles.append(muscle)
    place = split_label or (muscles[0] + "部" if muscles else "今天")
    if place in muscles:
        place = place + "部" if not place.endswith("部") and place in ("胸", "背", "肩", "腿") else place

    up = sum(1 for _, outcome, _ in named if outcome == "加重完成")
    load = "重量偏大" if up >= max(1, len(named) // 2) else "重量大体按计划"
    done_sets = [row for _, _, rows in named for row in rows if getattr(row, "completed", False)]
    tagged = [row for row in done_sets if getattr(row, "feeling", None)]
    hard_names = [name for name, outcome, _ in named if outcome in ("次数未达标", "没做完")]

    bits = [f"今天主要是{place}，{load}。"]
    if done_sets:
        if len(tagged) >= max(1, len(done_sets) // 2):
            bits.append(f"{len(tagged)} 组标了感觉。")
        elif tagged:
            bits.append(f"有 {len(tagged)} 组标了感觉。")
    if hard_names:
        bits.append("次数或组数没做够的有：" + "、".join(hard_names) + "。")
    extra = [m for m in muscles if not place.startswith(m) and m not in place]
    if extra:
        bits.append("另外练了" + "、".join(extra) + "。")
    notes = []
    for name, _, rows in named:
        for row in rows:
            text = (getattr(row, "note", None) or "").strip()
            if text:
                notes.append(f"做{name}时写的是「{text}」")
    if notes:
        bits.append("你的感受：" + "；".join(notes[:4]) + "。")
    if minutes is not None and 1 <= minutes <= 300:
        bits.append(f"实际训练 {minutes} 分钟。")
    return "".join(bits)


def pick_manual_feeling(sets: list[SetLike]) -> str | None:
    """已勾选组上的手动体感标签。力竭优先于合适、轻松。没打标返回 None。"""
    rank = {"力竭": 3, "合适": 2, "轻松": 1}
    found = [s.feeling for s in sets if s.completed and s.feeling in rank]
    if not found:
        return None
    return max(found, key=lambda f: rank[f])

