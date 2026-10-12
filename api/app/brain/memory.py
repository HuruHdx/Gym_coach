from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlmodel import Session, select

from app.config import settings
from app.exercises_catalog import find_exercises_in_text, roles_of
from app.models import ExerciseStats, Profile, TrainingSetLog
from app.taxonomy import Muscle, normalize_muscle


@dataclass
class Intent:
    expert: str  # training | profile | general
    muscles: list[str] = field(default_factory=list)
    raw: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryPack:
    profile_summary: str
    derived_summaries: list[str]
    recent_logs: list[str]
    token_estimate: int

    def as_prompt_block(self) -> str:
        parts = [
            "## 画像",
            self.profile_summary or "（尚无画像）",
            "## 相关派生",
            "\n".join(self.derived_summaries) or "（无派生）",
            "## 近期相关记录",
            "\n".join(self.recent_logs) or "（无历史）",
        ]
        return "\n".join(parts)


def estimate_tokens(text: str) -> int:
    # rough: ~1.5 chars / token for mixed CN/EN
    return max(1, int(len(text) / 1.5))


def build_profile_summary(profile: Profile | None) -> str:
    if not profile:
        return "用户尚未建立画像。"
    injuries = "、".join(profile.injuries) if profile.injuries else "无"
    prefs = "、".join(profile.preferences) if profile.preferences else "不限"
    height = f"{profile.height_cm:g}cm" if profile.height_cm else "未填"
    minutes = getattr(profile, "session_minutes", None) or 45
    return (
        f"目标={profile.goal.value}；经验={profile.experience.value}；"
        f"身高={height}；体重={profile.weight_kg}kg；"
        f"每周={profile.days_per_week}天；单次约={minutes}分钟；"
        f"器械偏好={prefs}；伤痛={injuries}"
    )


def apply_profile_defaults(intent: Intent, profile: Profile | None) -> Intent:
    """画像默认约束：本轮未点名器械时，用偏好；时长写入 params 供生成参考。"""
    if not profile:
        return intent
    params = dict(intent.params or {})
    prefs = [p for p in (profile.preferences or []) if p in ("器械", "自由重量", "绳索", "自重")]
    if prefs and not params.get("equipment"):
        # 四类都勾 ≈ 不限，不写死限制
        if set(prefs) != {"器械", "自由重量", "绳索", "自重"}:
            params["equipment"] = prefs
    minutes = getattr(profile, "session_minutes", None) or 45
    params.setdefault("session_minutes", minutes)
    return Intent(
        expert=intent.expert,
        muscles=list(intent.muscles),
        raw=intent.raw,
        params=params,
    )


def _extract_equipment(text: str) -> list[str] | None:
    """将口语场地/器械约束改写为目录 category 白名单。"""
    # 出差 / 酒店 / 家里 → 优先自重；提到哑铃则放宽到哑铃自由重量
    travel = any(k in text for k in ("出差", "酒店", "旅馆", "民宿"))
    home = any(k in text for k in ("家里", "居家", "在家"))
    bodyweight_only = any(k in text for k in ("徒手", "自重", "没器械", "没有器械"))
    dumbbell = any(k in text for k in ("哑铃", "只有哑铃", "就哑铃"))

    if bodyweight_only and not dumbbell:
        return ["自重"]
    if travel or home:
        return ["自重", "自由重量"] if dumbbell or "哑铃" in text else ["自重"]
    if dumbbell:
        return ["自由重量", "自重"]
    return None


def _wants_only_named(text: str) -> bool:
    """用户在收窄范围：只要点名的那几个，不要再铺一整堂。

    同时又说「再加腹肌」这类收尾时，不是只要那几个。
    """
    if any(k in text for k in ("还有", "加点", "加上", "再加", "最后", "收尾", "加一点", "顺便")):
        return False
    return any(
        k in text
        for k in (
            "只要",
            "只做",
            "只练",
            "主要做",
            "主要练",
            "就好了",
            "就这两个",
            "两个动作",
            "其他的",
            "下次再说",
            "别的不要",
            "不要其他",
            "其余不要",
        )
    )


def _extract_fatigue(text: str) -> bool:
    return any(
        k in text
        for k in ("没劲", "没力气", "累了", "好累", "疲劳", "很累", "状态差", "感冒", "力竭状态")
    )


def parse_intent(text: str) -> Intent:
    """意图改写：口语 → 结构化部位 / 器械 / 疲劳参数。"""
    t = text.strip()

    if any(k in t for k in ("画像", "体重", "目标改", "我是新手", "改成")):
        return Intent(expert="profile", raw=t)

    muscles: list[str] = []
    params: dict[str, Any] = {}

    focus = find_exercises_in_text(t)
    if focus:
        params["focus_exercises"] = focus
        if _wants_only_named(t):
            params["exclusive_focus"] = True

    # —— 复合部位展开（优先于单部位别名）——
    if any(k in t for k in ("上半身", "上肢")):
        muscles = [Muscle.CHEST.value, Muscle.BACK.value, Muscle.SHOULDER.value]
        params["split"] = "上半身"
    elif any(k in t for k in ("下半身", "下肢")):
        muscles = [Muscle.LEG.value, Muscle.CORE.value]
        params["split"] = "下半身"
    elif any(k in t for k in ("推日", "今天推", "今日推", "练推")):
        # 「推日」→ 胸+肩+臂（刻意不用单字「推」，避免误伤「卧推」）
        muscles = [Muscle.CHEST.value, Muscle.SHOULDER.value, Muscle.ARM.value]
        params["split"] = "推日"
    elif any(k in t for k in ("拉日", "今天拉", "今日拉", "练拉")):
        muscles = [Muscle.BACK.value, Muscle.ARM.value]
        params["split"] = "拉日"

    if not muscles:
        # 扫描全部单部位提及（可多选：如「胸背」）
        seen: list[str] = []
        for token, muscle in (
            ("胸", Muscle.CHEST),
            ("背", Muscle.BACK),
            ("肩", Muscle.SHOULDER),
            ("腿", Muscle.LEG),
            ("臀", Muscle.LEG),
            ("臂", Muscle.ARM),
            ("二头", Muscle.ARM),
            ("三头", Muscle.ARM),
            ("核心", Muscle.CORE),
            ("腹", Muscle.CORE),
            ("全身", Muscle.FULL),
        ):
            if token in t and muscle.value not in seen:
                seen.append(muscle.value)
        if seen:
            muscles = seen
        elif not focus:
            # 点了具体动作就不要再用整句猜部位（「硬拉」里的「拉」会误伤）
            m = normalize_muscle(t)
            if m:
                muscles = [m.value]

    equipment = _extract_equipment(t)
    if equipment:
        params["equipment"] = equipment
    if _extract_fatigue(t):
        params["fatigue"] = True
        params["deload"] = True
    if "随便" in t:
        params["flexible"] = True

    training_cue = any(k in t for k in ("练", "安排", "计划", "动作", "随便", "搞搞", "推日", "拉日"))
    if training_cue or muscles or equipment or params.get("fatigue"):
        return Intent(expert="training", muscles=muscles, raw=t, params=params)

    return Intent(expert="general", raw=t)


def _display_exercise(name: str, raw: str) -> str:
    """标题用用户嘴里的简称。说了「深蹲」就不要写成部位「腿」。"""
    for prefix in ("杠铃", "哑铃", "史密斯"):
        if name.startswith(prefix):
            short = name[len(prefix) :]
            if short and short in raw:
                return short
    return name


def _addon_label(raw: str, shown: list[str]) -> str | None:
    if any(k in raw for k in ("腹肌", "腹")) and not any("腹" in item for item in shown):
        return "腹肌"
    if "核心" in raw and "核心" not in shown:
        return "核心"
    return None


def draft_title_for_intent(intent: Intent) -> str | None:
    """课名：短、可预期；状态（草稿/已采纳）由前端角标表达，不写「今日草稿」。"""
    focus = intent.params.get("focus_exercises") or []
    if focus:
        shown = [_display_exercise(name, intent.raw) for name in focus]
        if not intent.params.get("exclusive_focus"):
            extra = _addon_label(intent.raw, shown)
            if extra:
                shown.append(extra)
        return "、".join(shown)

    split = intent.params.get("split")
    if isinstance(split, str) and split:
        return split

    muscles = list(intent.muscles or [])
    if not muscles:
        return None
    if "全身" in muscles and len(muscles) == 1:
        return "全身训"
    if len(muscles) == 1:
        return f"{muscles[0]}训"
    return "+".join(muscles)


def format_intent_for_prompt(intent: Intent) -> str:
    """把结构化意图写成模型可读的约束说明。"""
    parts = [f"专家={intent.expert}"]
    title = draft_title_for_intent(intent)
    if intent.params.get("focus_exercises"):
        if intent.muscles:
            parts.append(f"用户点名部位={'+'.join(intent.muscles)}")
        if title:
            parts.append(f"标题={title}")
            parts.append("标题规则=必须用上面的标题，不要写成腿+背或其他肌肉拼接")
        briefs = []
        for name in intent.params["focus_exercises"]:
            roles = roles_of(name) or ["—"]
            briefs.append(f"{name}可作{'/'.join(roles)}")
        parts.append("点名动作=" + "+".join(intent.params["focus_exercises"]))
        parts.append("动作用法=" + "；".join(briefs) + "。meta.muscle 由你按用户这句话从可作里选，目录默认不是本堂答案")
    elif intent.muscles:
        parts.append(f"部位={'+'.join(intent.muscles)}")
    if intent.params.get("split"):
        parts.append(f"分化={intent.params['split']}")
    if intent.params.get("equipment"):
        parts.append(f"器械限制={','.join(intent.params['equipment'])}（勿推荐场馆固定器械/绳索）")
    if intent.params.get("session_minutes"):
        parts.append(f"单次时长≈{intent.params['session_minutes']}分钟（控制动作数量与组数密度）")
    if intent.params.get("fatigue"):
        parts.append("状态=疲劳/降阶（勿加重，优先低轴向负荷与控组）")
    if intent.params.get("flexible"):
        parts.append("灵活=可简短凑合练")
    if intent.params.get("exclusive_focus"):
        parts.append("范围=只排点名动作，不要再加其他动作")
    return "；".join(parts)


def assemble_memory(
    session: Session,
    intent: Intent,
    profile: Profile | None,
    top_n: int = 5,
) -> MemoryPack:
    profile_summary = build_profile_summary(profile)
    derived: list[str] = []
    logs: list[str] = []

    # Always a bit of global derived context
    stats = session.exec(select(ExerciseStats).limit(8)).all()
    for s in stats:
        feel_str = f" 体感={s.last_feeling}" if s.last_feeling else ""
        outcome_str = f" 表现={s.last_outcome}" if s.last_outcome else ""
        derived.append(
            f"{s.exercise_name}: 上次={s.last_weight}kg×{s.last_reps or '-'}{feel_str}{outcome_str} 最好={s.best_weight} 趋势={s.trend}"
        )

    if intent.muscles:
        # Prefer stats / logs matching muscle tags on set logs
        q = (
            select(TrainingSetLog)
            .where(TrainingSetLog.muscle.in_(intent.muscles))  # type: ignore[attr-defined]
            .order_by(TrainingSetLog.id.desc())
            .limit(top_n)
        )
        rows = session.exec(q).all()
        for r in rows:
            feel = f" feel={r.feeling}" if r.feeling else ""
            logs.append(
                f"{r.exercise_name} set#{r.set_index} "
                f"计划={r.target_weight}kg×{r.target_reps or '-'} "
                f"实际={r.actual_weight or r.target_weight}kg×{r.actual_reps or '-'} "
                f"done={r.completed}{feel}"
            )
        # filter derived to related names if possible
        related = [d for d in derived if any(m in d for m in intent.muscles)]
        if related:
            derived = related[:6]

    pack = MemoryPack(
        profile_summary=profile_summary,
        derived_summaries=derived[:8],
        recent_logs=logs[:top_n],
        token_estimate=0,
    )
    pack.token_estimate = estimate_tokens(pack.as_prompt_block())

    # Budget trim
    budget = settings.memory_token_budget
    while pack.token_estimate > budget and pack.recent_logs:
        pack.recent_logs.pop()
        pack.token_estimate = estimate_tokens(pack.as_prompt_block())
    while pack.token_estimate > budget and len(pack.derived_summaries) > 1:
        pack.derived_summaries.pop()
        pack.token_estimate = estimate_tokens(pack.as_prompt_block())

    return pack
