"""对话里出现的事实：列表合并；单值先问再覆盖；只对今天有效的不进档案。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.exercises_catalog import find_catalog_mentions_in_text
from app.models import Experience, Goal, PendingMemory, Profile, ProfileHistory, utcnow

_INJURIES = ("膝盖", "腰", "肩", "手腕", "肘", "踝")
_STANDING_AVOID = (
    "以后都",
    "以后别",
    "以后不",
    "以后不要",
    "一直别",
    "再也不",
    "我们健身房没有",
    "我家健身房没有",
    "这家健身房没有",
    "店里没有",
)
_GOAL_BY_WORD = {"增肌": Goal.BULK, "减脂": Goal.CUT, "减肥": Goal.CUT, "力量": Goal.STRENGTH, "塑形": Goal.SHAPE}
_LEVEL_BY_WORD = {
    "新手": Experience.NOVICE,
    "入门": Experience.NOVICE,
    "进阶": Experience.INTERMEDIATE,
    "老炮": Experience.ADVANCED,
    "多年训练": Experience.ADVANCED,
}
_CONFIRM = {"要", "好", "好的", "改吧", "确认", "对", "是", "是的", "嗯", "行", "可以", "改"}
_REJECT = ("不用", "算了", "别改", "不要改", "先不改", "取消")


@dataclass
class MemoryEffect:
    note: str = ""
    applied: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    return text.strip().strip("。！!？?，, ")


def _is_confirm(text: str) -> bool:
    head = _clean(text)
    if any(mark in head for mark in _REJECT):
        return False
    if head in _CONFIRM:
        return True
    return head.startswith(("要，", "要,", "好的，", "确认，", "改吧"))


def _is_reject(text: str) -> bool:
    return any(mark in text for mark in _REJECT)


def _pending(session: Session) -> PendingMemory | None:
    return session.exec(select(PendingMemory).order_by(PendingMemory.id.desc())).first()


def _clear_pending(session: Session, row: PendingMemory | None) -> None:
    if row is not None:
        session.delete(row)


def _ask(session: Session, profile_field: str, old: str, new: str, question: str) -> MemoryEffect:
    existing = _pending(session)
    _clear_pending(session, existing)
    session.add(PendingMemory(field=profile_field, old_value=old, new_value=new))
    session.commit()
    return MemoryEffect(note=question)


def _apply_pending(session: Session, profile: Profile, row: PendingMemory) -> MemoryEffect:
    field_name = row.field
    new_raw = row.new_value
    old_raw = row.old_value
    if field_name == "weight_kg":
        profile.weight_kg = float(new_raw)
    elif field_name == "goal":
        profile.goal = Goal(new_raw)
    elif field_name == "experience":
        profile.experience = Experience(new_raw)
    elif field_name == "days_per_week":
        profile.days_per_week = int(new_raw)
    elif field_name == "session_minutes":
        profile.session_minutes = int(new_raw)
    else:
        _clear_pending(session, row)
        session.commit()
        return MemoryEffect()
    session.add(ProfileHistory(field=field_name, old_value=old_raw, new_value=new_raw))
    profile.updated_at = utcnow()
    session.add(profile)
    _clear_pending(session, row)
    session.commit()
    label = {
        "weight_kg": "体重",
        "goal": "长期目标",
        "experience": "训练经验",
        "days_per_week": "每周天数",
        "session_minutes": "单次时长",
    }.get(field_name, field_name)
    return MemoryEffect(note=f"已把{label}更新为 {new_raw}。", applied=[field_name])


def _merge_unique(current: list[str] | None, name: str) -> list[str] | None:
    items = list(current or [])
    if name in items:
        return None
    items.append(name)
    return items


def _drop_name(current: list[str] | None, name: str) -> list[str] | None:
    items = list(current or [])
    if name not in items:
        return None
    return [item for item in items if item != name]


def _injuries(text: str) -> tuple[list[str], list[str]]:
    add: list[str] = []
    remove: list[str] = []
    for name in _INJURIES:
        if re.search(rf"{name}.{{0,4}}(好了|不疼了|不痛了|没事了)", text):
            remove.append(name)
            continue
        if re.search(rf"{name}.{{0,6}}(疼|痛|不舒服|有伤|受伤|不好|有问题)", text) or re.search(
            rf"(伤了|伤到|扭了).{{0,4}}{name}", text
        ):
            add.append(name)
    return add, remove


def _standing_avoid(text: str) -> list[str]:
    if not any(cue in text for cue in _STANDING_AVOID):
        return []
    return find_catalog_mentions_in_text(text)


def _single_value_proposal(text: str, profile: Profile) -> tuple[str, str, str, str] | None:
    """返回 field, old, new, question。没有明确的新值则 None。"""
    weight = re.search(r"(?:体重|重了|现在是?)\s*(\d{2,3}(?:\.\d)?)\s*(?:kg|公斤|千克)?", text, re.I)
    if weight is None:
        weight = re.search(r"(\d{2,3}(?:\.\d)?)\s*(?:kg|公斤|千克)", text, re.I)
    if weight and any(mark in text for mark in ("体重", "公斤", "千克", "kg", "KG")):
        new = float(weight.group(1))
        if abs(new - float(profile.weight_kg)) > 0.05:
            return (
                "weight_kg",
                f"{profile.weight_kg:g}",
                f"{new:g}",
                f"档案里体重是 {profile.weight_kg:g}kg，要改成 {new:g}kg 吗？",
            )
    goal = re.search(r"(?:长期)?目标(?:改成|改为|换成)\s*(增肌|减脂|减肥|力量|塑形)", text)
    if goal is None:
        goal = re.search(r"(?:改成|改为)\s*(增肌|减脂|减肥|力量|塑形)(?:目标)?", text)
    if goal:
        chosen = _GOAL_BY_WORD[goal.group(1)]
        if chosen != profile.goal:
            return (
                "goal",
                profile.goal.value,
                chosen.value,
                f"档案里长期目标是{profile.goal.value}，要改成{chosen.value}吗？",
            )
    level = re.search(r"经验(?:改成|改为)\s*(新手|入门|进阶|老炮|多年训练)", text)
    if level:
        chosen_level = _LEVEL_BY_WORD[level.group(1)]
        if chosen_level != profile.experience:
            return (
                "experience",
                profile.experience.value,
                chosen_level.value,
                f"档案里训练经验是{profile.experience.value}，要改成{chosen_level.value}吗？",
            )
    days = re.search(r"每周(?:练)?\s*(\d)\s*天", text)
    if days and any(mark in text for mark in ("以后", "改成", "改为")):
        new_days = int(days.group(1))
        if 1 <= new_days <= 7 and new_days != profile.days_per_week:
            return (
                "days_per_week",
                str(profile.days_per_week),
                str(new_days),
                f"档案里每周 {profile.days_per_week} 天，要改成每周 {new_days} 天吗？",
            )
    minutes = re.search(r"(?:每次|单次)(?:练)?\s*(\d{2,3})\s*分钟", text)
    if minutes and any(mark in text for mark in ("以后", "改成", "改为")):
        new_minutes = int(minutes.group(1))
        current = profile.session_minutes or 45
        if 15 <= new_minutes <= 180 and new_minutes != current:
            return (
                "session_minutes",
                str(current),
                str(new_minutes),
                f"档案里单次约 {current} 分钟，要改成 {new_minutes} 分钟吗？",
            )
    return None


def apply_user_memory(session: Session, user_text: str) -> MemoryEffect:
    profile = session.exec(select(Profile).limit(1)).first()
    if profile is None:
        return MemoryEffect()
    text = user_text.strip()
    pending = _pending(session)
    if pending is not None and _is_reject(text):
        _clear_pending(session, pending)
        session.commit()
        return MemoryEffect(note="那先不改档案。")
    if pending is not None and _is_confirm(text):
        return _apply_pending(session, profile, pending)

    notes: list[str] = []
    applied: list[str] = []

    add_injuries, remove_injuries = _injuries(text)
    injuries = list(profile.injuries or [])
    changed = False
    for name in remove_injuries:
        if name in injuries:
            injuries = [item for item in injuries if item != name]
            changed = True
            notes.append(f"已从伤痛里去掉{name}。")
    for name in add_injuries:
        if name not in injuries and name not in remove_injuries:
            injuries.append(name)
            changed = True
            notes.append(f"已记上伤痛：{name}。")
    if changed:
        profile.injuries = injuries
        applied.append("injuries")

    avoid = list(profile.avoid_exercises or [])
    avoid_changed = False
    for name in _standing_avoid(text):
        if name not in avoid:
            avoid.append(name)
            avoid_changed = True
            notes.append(f"已记下以后避开：{name}。")
    if avoid_changed:
        profile.avoid_exercises = avoid
        applied.append("avoid_exercises")

    if applied:
        profile.updated_at = utcnow()
        session.add(profile)
        session.commit()

    proposal = _single_value_proposal(text, profile)
    if proposal:
        field_name, old, new, question = proposal
        asked = _ask(session, field_name, old, new, question)
        notes.append(asked.note)
    return MemoryEffect(note="".join(notes), applied=applied)
