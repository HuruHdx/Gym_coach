from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlmodel import Session, select

from app.config import settings
from app.exercises_catalog import (
    format_candidates_block,
    modalities_of,
    retrieve_candidates,
    roles_of,
)
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
    candidates_block: str = ""

    def as_prompt_block(self) -> str:
        """空派生/记录整段省略，少占 token。"""
        parts = ["【长期记忆】", self.profile_summary or "档案：无"]
        if self.derived_summaries:
            parts.append("相关训练：\n" + "\n".join(self.derived_summaries))
        if self.recent_logs:
            parts.append("最近组记录：\n" + "\n".join(self.recent_logs))
        if self.candidates_block:
            parts.append(self.candidates_block)
        return "\n".join(parts)


def estimate_tokens(text: str) -> int:
    # rough: ~1.5 chars / token for mixed CN/EN
    return max(1, int(len(text) / 1.5))


def session_modalities(intent: Intent) -> list[str]:
    mods = list(intent.params.get("modality") or [])
    if not mods and intent.params.get("cardio"):
        return ["有氧"]
    return mods


def is_strength_session(intent: Intent) -> bool:
    """无课型时按抗阻记；明确只有有氧/HIIT/灵活性则非力量课。"""
    mods = session_modalities(intent)
    if not mods:
        return True
    return "抗阻" in mods


# 画像枚举 → 模型可读的属性语义（不出现「老炮」等选项名，减少被当成昵称）
_LEVEL_FOR_PROMPT = {"新手": "入门阶段", "进阶": "有训练基础", "老炮": "多年训练"}

# 所有对话类提示词共用：结构化说明字段语义与用途
PROFILE_FIELD_GUIDE = """【学员属性怎么用】
以下字段是系统传入的学员客观参数，仅供你在内部决策（选动作、定强度、判分流）时参考，绝不是用户的姓名、昵称或头衔：
- 训练经验档位（入门阶段 / 有训练基础 / 多年训练）：用于决定动作复杂度与是否追问分化侧重
- 长期目标（增肌 / 减脂 / 力量 / 塑形）：长期周期背景，不等于本堂课型（如增肌期也可做有氧）
- 身体与偏好（身高 / 体重 / 单次时长 / 器械偏好 / 伤痛）：用于约束负荷、容量与动作筛选"""

# 喂给模型的近轮对话上限（轮≈一来一回里的一条）
_DIALOGUE_MAX_TURNS = 12
_DIALOGUE_MAX_CHARS = 1800


def format_dialogue_for_prompt(history: list[Any] | None, *, max_turns: int = _DIALOGUE_MAX_TURNS) -> str:
    """把近几轮对话压成短上下文。history 为 dict / 带属性对象均可。"""
    if not history:
        return ""
    turns = list(history)[-max_turns:]
    lines: list[str] = []
    for turn in turns:
        if isinstance(turn, dict):
            role = turn.get("role") or "user"
            text = str(turn.get("text") or "").strip()
            card_title = turn.get("card_title")
            card_items = turn.get("card_items") or []
        else:
            role = getattr(turn, "role", None) or "user"
            text = str(getattr(turn, "text", "") or "").strip()
            card_title = getattr(turn, "card_title", None)
            card_items = getattr(turn, "card_items", None) or []
        who = "用户" if role == "user" else "教练"
        bit = text
        if role == "assistant" and (card_title or card_items):
            items = "、".join(str(x) for x in list(card_items)[:8])
            card_bit = f"草稿《{card_title or '训练'}》"
            if items:
                card_bit += f"：{items}"
            bit = f"{text}（{card_bit}）" if text else card_bit
        if bit:
            lines.append(f"{who}：{bit[:280]}")
    body = "\n".join(lines)
    if len(body) > _DIALOGUE_MAX_CHARS:
        body = body[-_DIALOGUE_MAX_CHARS:]
        cut = body.find("\n")
        if cut > 0:
            body = body[cut + 1 :]
    if not body.strip():
        return ""
    return (
        "【近期对话】（按时间从旧到新；请结合这些轮次理解指代和是否在改上一张计划）\n"
        f"{body}\n"
    )


def _level_phrase(experience: object) -> str:
    raw = experience.value if hasattr(experience, "value") else str(experience)
    return _LEVEL_FOR_PROMPT.get(raw, raw)


_ALL_GEAR = frozenset({"自由重量", "器械", "绳索", "自重"})


def _as_name_list(value: Any) -> list[str]:
    """画像列表字段。库里偶发把 JSON 存成字符串 '[]'，不能原样写进提示词。"""
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw or raw in ("[]", "null"):
            return []
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return [raw]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in ("[]", "null"):
            out.append(text)
    return out


def format_profile_for_llm(
    profile: Profile | None,
    *,
    modalities: list[str] | None = None,
) -> str:
    """档案数据本身。字段怎么用写在系统提示词里，不放进用户消息。"""
    del modalities  # 课型不再决定档案里藏哪些字段
    if not profile:
        return "档案：无"
    injuries = _as_name_list(profile.injuries)
    prefs = _as_name_list(profile.preferences)
    avoid = _as_name_list(getattr(profile, "avoid_exercises", None))
    # 选「健身房」会存下四类标签，意思是都能用，不是四项偏好
    if not prefs or _ALL_GEAR <= set(prefs):
        gear = "不限（选了健身房：四类都能用，不是偏好排序）"
    else:
        gear = "、".join(prefs)
    injury = "、".join(injuries) if injuries else "未填"
    height = f"{profile.height_cm:g}cm" if profile.height_cm else "未填"
    weight = f"{profile.weight_kg:g}kg" if profile.weight_kg is not None else "未填"
    raw_minutes = getattr(profile, "session_minutes", None)
    minutes = f"{int(raw_minutes)}分钟" if raw_minutes is not None else "未填"
    level = _level_phrase(profile.experience)
    line = (
        f"训练经验：{level}；长期目标：{profile.goal.value}；"
        f"身高：{height}；体重：{weight}；"
        f"每周：{profile.days_per_week}天；单次约：{minutes}；"
        f"可用器械：{gear}；伤痛：{injury}"
    )
    if avoid:
        line += f"；以后避开：{'、'.join(avoid)}"
    return f"档案：{line}"


def build_profile_summary(
    profile: Profile | None,
    *,
    modalities: list[str] | None = None,
) -> str:
    """兼容旧调用；实际拼进提示词时优先用 format_profile_for_llm。"""
    return format_profile_for_llm(profile, modalities=modalities)


def _utterance_session_minutes(raw: str) -> int | None:
    """本句是否明示了分钟数。意图模型爱瞎填 40，不能当用户说的。"""
    hit = re.search(r"(\d{1,3})\s*分钟", raw or "")
    if not hit:
        return None
    minutes = int(hit.group(1))
    if 15 <= minutes <= 180:
        return minutes
    return None


def _apply_session_minutes(params: dict[str, Any], raw: str, profile: Profile | None) -> None:
    """时长优先级：本句明示 > 画像已填 > 未指定（清掉模型瞎填的 40）。"""
    spoken_minutes = _utterance_session_minutes(raw)
    if spoken_minutes is not None:
        params["session_minutes"] = spoken_minutes
        params["minutes_source"] = "utterance"
        return
    profile_minutes = getattr(profile, "session_minutes", None) if profile else None
    if profile_minutes is not None and 15 <= int(profile_minutes) <= 180:
        params["session_minutes"] = int(profile_minutes)
        params["minutes_source"] = "profile"
        return
    # 画像未填且本句没提：不要用模型臆造的分钟数
    params.pop("session_minutes", None)
    params["minutes_source"] = "unset"


def apply_profile_defaults(intent: Intent, profile: Profile | None) -> Intent:
    """画像默认约束：器械偏好、时长；本句没说 goal 时，抗阻课才回落画像目标。"""
    params = dict(intent.params or {})
    _apply_session_minutes(params, intent.raw or "", profile)
    if not profile:
        return Intent(
            expert=intent.expert,
            muscles=list(intent.muscles),
            raw=intent.raw,
            params=params,
        )
    prefs = [p for p in (profile.preferences or []) if p in ("器械", "自由重量", "绳索", "自重")]
    if prefs and not params.get("equipment"):
        # 四类都勾 ≈ 不限，不写死限制
        if set(prefs) != {"器械", "自由重量", "绳索", "自重"}:
            params["equipment"] = prefs

    spoken = _extract_goal(intent.raw or "")
    if spoken:
        params["goal"] = spoken
        params["goal_source"] = "utterance"
    else:
        # 「暴汗练心肺」不是在改长期目标；模型猜的减脂丢掉
        params.pop("goal", None)
        params.pop("goal_source", None)

    mods = list(params.get("modality") or [])
    if not mods and params.get("cardio"):
        mods = ["有氧"]
    pure_non_strength = bool(mods) and "抗阻" not in mods

    if not params.get("goal") and getattr(profile, "goal", None) is not None:
        goal_val = profile.goal.value if hasattr(profile.goal, "value") else str(profile.goal)
        if goal_val in ("增肌", "减脂", "力量", "塑形"):
            if pure_non_strength:
                # 有氧/拉伸课不把画像增肌写进本堂目标
                pass
            else:
                params["goal"] = goal_val
                params["goal_source"] = "profile"
                travel = any(k in (intent.raw or "") for k in ("出差", "酒店", "旅馆", "民宿"))
                tension = params.get("tension")
                held = isinstance(tension, dict) and tension.get("has_tension")
                # 路由已经决定要反问时，不要因为补了画像目标就把 ready 抬成 true
                if (
                    intent.expert == "training"
                    and params.get("agent") == "coach_plan"
                    and not travel
                    and not held
                ):
                    params["ready"] = True
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


def _said_without_negation(text: str, keyword: str) -> bool:
    """「不想上重量」里的关键词不算正向目标。"""
    start = 0
    while True:
        index = text.find(keyword, start)
        if index < 0:
            return False
        prefix = text[max(0, index - 4) : index]
        if not any(mark in prefix for mark in ("不", "别", "没", "勿", "无")):
            return True
        start = index + len(keyword)


def _extract_fatigue(text: str) -> bool:
    return any(
        k in text
        for k in ("没劲", "没力气", "累了", "好累", "疲劳", "很累", "状态差", "感冒", "力竭状态")
    )


def parse_intent(text: str) -> Intent:
    """规则兜底：口语 → agent + 部位 / 器械 / 疲劳。"""
    t = text.strip()

    if any(
        k in t
        for k in ("怎么吃", "吃什么", "饮食", "热量", "碳水", "营养师", "减脂餐", "增肌餐", "蛋白粉", "补剂")
    ) or ("蛋白" in t and "练" not in t):
        return Intent(
            expert="nutrition",
            raw=t,
            params={"agent": "nutrition", "ready": True},
        )

    if any(k in t for k in ("画像", "目标改", "我是新手")):
        return Intent(
            expert="chat",
            raw=t,
            params={"agent": "coach_chat", "ready": True},
        )

    muscles: list[str] = []
    params: dict[str, Any] = {}

    if any(k in t for k in ("上半身", "上肢")):
        muscles = [Muscle.CHEST.value, Muscle.BACK.value, Muscle.SHOULDER.value]
        params["split"] = "上半身"
    elif any(k in t for k in ("下半身", "下肢")):
        muscles = [Muscle.LEG.value, Muscle.CORE.value]
        params["split"] = "下半身"
    elif any(k in t for k in ("推日", "今天推", "今日推", "练推")):
        muscles = [Muscle.CHEST.value, Muscle.SHOULDER.value, Muscle.ARM.value]
        params["split"] = "推日"
    elif any(k in t for k in ("拉日", "今天拉", "今日拉", "练拉")):
        muscles = [Muscle.BACK.value, Muscle.ARM.value]
        params["split"] = "拉日"

    if not muscles:
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
        else:
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

    goal = _extract_goal(t)
    if goal:
        params["goal"] = goal

    modality = _extract_modalities(t)
    if modality:
        params["modality"] = modality
        if "有氧" in modality:
            params["cardio"] = True
            params["session_style"] = "cardio"
        if ("有氧" in modality or "HIIT" in modality) and "抗阻" not in modality and not muscles:
            muscles = [Muscle.FULL.value]
        if "抗阻" not in modality and muscles and any(m in muscles for m in ("胸", "背", "肩", "腿", "臂")):
            # 点了部位默认补抗阻
            if "灵活性" not in modality or any(k in t for k in ("练", "推", "拉")):
                modality = list(dict.fromkeys([*modality, "抗阻"]))
                params["modality"] = modality
    elif _is_cardio(t):
        params["cardio"] = True
        params["session_style"] = "cardio"
        params["modality"] = ["有氧"]
        if not muscles:
            muscles = [Muscle.FULL.value]

    # 点了部位/分化但还没课型 → 抗阻
    if (muscles or params.get("split")) and not params.get("modality"):
        params["modality"] = ["抗阻"]

    plan_cue = any(
        k in t
        for k in (
            "练",
            "安排",
            "计划",
            "排一堂",
            "随便",
            "搞搞",
            "推日",
            "拉日",
            "有氧",
            "出汗",
            "拉伸",
            "HIIT",
            "hiit",
            "间歇",
        )
    )
    chat_cue = any(
        k in t
        for k in (
            "什么是",
            "怎么做",
            "怎么避免",
            "为什么",
            "该怎么练",
            "应该怎么练",
            "上次",
            "多重",
            "多少kg",
            "RIR",
            "RPE",
            "离心",
            "向心",
            "要领",
            "能不能练",
            "如何",
            "怎样",
        )
    )

    # 点了动作名但在问知识（深蹲怎么避免内扣）→ 闲聊，不排课
    if chat_cue and not plan_cue:
        return Intent(expert="chat", raw=t, params={"agent": "coach_chat", "ready": True})
    # 「减脂该怎么练」这类求知识，即使有 goal 也不排课
    if chat_cue and goal and not any(k in t for k in ("安排", "排一堂", "计划", "帮我排", "出个")):
        if not muscles and not params.get("cardio"):
            return Intent(expert="chat", raw=t, params={"agent": "coach_chat", "ready": True})

    if (
        plan_cue
        or muscles
        or equipment
        or params.get("fatigue")
        or params.get("cardio")
        or params.get("modality")
        or params.get("goal")
    ):
        params["agent"] = "coach_plan"
        params["ready"] = bool(
            muscles
            or params.get("cardio")
            or params.get("split")
            or params.get("modality")
            or params.get("goal")
        )
        return Intent(expert="training", muscles=muscles, raw=t, params=params)

    return Intent(expert="chat", raw=t, params={"agent": "coach_chat", "ready": True})


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


def _is_cardio(text: str) -> bool:
    # 「出汗」口语太宽，不能等同有氧；只有明确课型/器械词才算
    # 「没有划船机」里的器械名不算正向点有氧
    return any(
        _said_without_negation(text, k)
        for k in ("有氧", "跑步", "慢跑", "跳绳", "单车", "椭圆", "划船机", "爬楼")
    )


def _extract_modalities(text: str) -> list[str] | None:
    """规则层课型识别；可多项。"""
    found: list[str] = []
    stretch = any(k in text for k in ("拉伸", "活动度", "舒展", "柔韧", "灵活性"))
    # 「放松」常跟拉伸一起；单独「放松一下」也算灵活性
    if stretch or ("放松" in text and not any(k in text for k in ("胸", "背", "腿", "推", "拉"))):
        found.append("灵活性")
    if any(k in text for k in ("HIIT", "hiit", "间歇", "循环燃脂", "波比", "战绳")):
        found.append("HIIT")
    if _is_cardio(text):
        found.append("有氧")
    strength_cue = any(
        k in text
        for k in (
            "练胸",
            "练背",
            "练肩",
            "练腿",
            "练臂",
            "力量",
            "推日",
            "拉日",
            "抗阻",
            "增肌",
            "上半身",
            "下半身",
            "硬拉",
            "深蹲",
            "卧推",
        )
    )
    named_part = any(k in text for k in ("胸", "背", "肩", "腿", "臂", "核心", "腹"))
    # 点了部位：默认抗阻；纯拉伸例外
    if strength_cue or (named_part and not stretch):
        found.append("抗阻")
    elif named_part and stretch and any(k in text for k in ("练", "推", "拉")):
        found.append("抗阻")
    return found or None


def _extract_goal(text: str) -> str | None:
    if any(_said_without_negation(text, k) for k in ("减脂", "减肥", "燃脂")):
        return "减脂"
    if any(_said_without_negation(text, k) for k in ("增肌", "长肉", "充血")):
        return "增肌"
    if any(_said_without_negation(text, k) for k in ("力量", "变强", "上重量")):
        return "力量"
    if any(_said_without_negation(text, k) for k in ("塑形", "线条")):
        return "塑形"
    if any(_said_without_negation(text, k) for k in ("恢复", "康复")):
        return "恢复"
    return None


def draft_title_for_intent(intent: Intent) -> str | None:
    """课名：短、可预期；状态（草稿/已采纳）由前端角标表达，不写「今日草稿」。"""
    modality = intent.params.get("modality") or []
    focus = intent.params.get("focus_exercises") or []
    named_part = any(k in (intent.raw or "") for k in ("胸", "背", "肩", "腿", "臂", "核心"))

    if focus:
        shown = [_display_exercise(name, intent.raw) for name in focus]
        if not intent.params.get("exclusive_focus"):
            extra = _addon_label(intent.raw, shown)
            if extra:
                shown.append(extra)
        return "、".join(shown)

    # 非抗阻主课：用课型当标题，避免硬套「全身训」
    if not named_part and not intent.params.get("split"):
        if "有氧" in modality and "抗阻" not in modality and "HIIT" not in modality:
            return "有氧"
        if "HIIT" in modality and "抗阻" not in modality:
            return "HIIT"
        if "灵活性" in modality and "抗阻" not in modality:
            return "拉伸"
        if intent.params.get("cardio"):
            return "有氧"

    split = intent.params.get("split")
    if isinstance(split, str) and split:
        return split

    muscles = list(intent.muscles or [])
    if not muscles:
        if intent.params.get("goal") == "减脂":
            return "减脂训"
        return None
    if "全身" in muscles and len(muscles) == 1:
        return "全身训"
    if len(muscles) == 1:
        return f"{muscles[0]}训"
    return "+".join(muscles)


# 排除动作不另开字段。原话里出现替换说法就补同类；只说删掉就不补。
_REPLACE_CUES = ("换成", "换掉", "换一个", "换个", "没有", "用不了", "做不了", "没法")
_DROP_CUES = ("去掉", "删掉", "删除", "删了", "拿掉", "不要这个", "不要了", "不做这个", "别排")


def classify_exclude_mode(text: str) -> str | None:
    """原话同时出现「去掉」和「换成」时算替换。都没有就返回 None。"""
    raw = text or ""
    if any(cue in raw for cue in _REPLACE_CUES):
        return "replace"
    if any(cue in raw for cue in _DROP_CUES):
        return "drop"
    return None


def stamp_exclude_mode(intent: Intent) -> None:
    """有排除项时写入 drop / replace，供提示词和校验共用。"""
    if not (intent.params or {}).get("exclude_exercises"):
        return
    mode = intent.params.get("exclude_mode")
    if mode in ("drop", "replace"):
        return
    intent.params["exclude_mode"] = classify_exclude_mode(intent.raw or "") or "replace"


def format_intent_for_prompt(intent: Intent, profile: Profile | None = None) -> str:
    """把结构化意图写成模型可读的约束说明（不含路由字段 agent/ready）。"""
    parts: list[str] = []
    qa_kind = intent.params.get("qa_kind")
    if qa_kind == "decide":
        parts.append("这一问=个人决策，结论要落到长期记忆里的档案字段")
    elif qa_kind == "recall":
        parts.append("这一问=查本人记录，没有记录就说明没有")
    elif qa_kind == "explain":
        parts.append("这一问=讲解动作或知识")
    relation = intent.params.get("draft_relation")
    session_target = intent.params.get("session_target")
    if session_target == "keep":
        parts.append("与上一张计划的关系=部位保持上一张，只重排动作，不要沿用上一张的具体动作")
        if intent.params.get("has_focus_detail"):
            parts.append("侧重=沿用短期记忆里上一张已经写明的侧重，不要改口径，也不要再追问")
    elif session_target == "ask":
        parts.append("与上一张计划的关系=先确认部位去留，不要默认放弃当前部位")
    elif relation == "fresh" or session_target == "switch":
        parts.append("与上一张计划的关系=放弃上一张，重排一堂新课，不要沿用上一张的动作")
    elif relation == "revise":
        parts.append("与上一张计划的关系=只改上一张里用户点到的内容，其余保留")
    modality = session_modalities(intent)
    strength = is_strength_session(intent)

    # 本堂目标：抗阻课可带画像目标；非抗阻也可用本句点名的目标（如减脂有氧）
    # 经验档位已在画像块里说明，这里不再重复写，避免模型当成称呼
    if intent.params.get("goal"):
        from_profile = intent.params.get("goal_source") == "profile"
        if strength or not from_profile:
            src = "画像" if from_profile else "本句"
            parts.append(f"目标={intent.params['goal']}（来自{src}）")

    if modality:
        parts.append(f"课型={'+'.join(modality)}")
    elif intent.params.get("cardio"):
        parts.append("课型=有氧")

    if intent.params.get("intensity") == "low":
        parts.append("强度偏好=低强度恢复(RPE5-6)")
    elif intent.params.get("intensity_demand") == "heavy":
        parts.append(
            "强度=用户坚持加重（尽管有伤）：改成更低次数、更大重量。"
            "text 只写按你的要求加重了，伤处不适就停。不要改成有氧"
        )
    elif intent.params.get("intensity") == "high":
        if strength:
            parts.append("强度=把这堂抗阻练难一点（可加组或略增重量）。不要写成有氧或心肺冲刺")
        else:
            parts.append("强度偏好=高强度心肺(RPE7-8)")

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
        parts.append(
            "动作用法=" + "；".join(briefs) + "。meta.muscle 由你按用户这句话从可作里选，目录默认不是本堂答案"
        )
    elif intent.muscles:
        # 纯有氧/HIIT 的「全身」是占位，不写进提示词
        if not (not strength and intent.muscles == ["全身"]):
            parts.append(f"部位={'+'.join(intent.muscles)}")

    if intent.params.get("split"):
        parts.append(f"分化={intent.params['split']}")
    if intent.params.get("equipment"):
        parts.append(f"器械限制={','.join(intent.params['equipment'])}（勿推荐场馆固定器械/绳索）")
    if intent.params.get("session_minutes"):
        mins = intent.params["session_minutes"]
        src = intent.params.get("minutes_source")
        src_note = "来自本句" if src == "utterance" else "来自学员档案"
        if strength:
            parts.append(
                f"单次时长={mins}分钟（{src_note}；只用来控制动作数量与组数，"
                f"回复里不要硬写「{mins}分钟」。短期记忆里别的分钟数不要拿来改这个时长）"
            )
        else:
            parts.append(
                f"单次时长={mins}分钟（{src_note}；按此时长排，回复里不要硬写分钟数，也不要改成别的默认）"
            )
    elif intent.params.get("minutes_source") == "unset":
        parts.append(
            "单次时长=未指定（档案未填且本句未提；可按常规单次容量排，"
            "文案不要硬写「40分钟」；若需要可先问一句想练多久）"
        )
    if intent.params.get("fatigue"):
        parts.append("状态=疲劳/降阶（勿加重，优先低轴向负荷与控组）")
    if intent.params.get("flexible"):
        parts.append("灵活=可简短凑合练")
    if intent.params.get("exclusive_focus"):
        parts.append("范围=只排点名动作，不要再加其他动作")
    if intent.params.get("exclude_exercises"):
        stamp_exclude_mode(intent)
        names = "+".join(intent.params["exclude_exercises"])
        if intent.params.get("exclude_mode") == "drop":
            parts.append(
                f"排除动作={names}（只删除，不要补同类，不要问是不是想少练；课可以变短）"
            )
        else:
            terms = [part for part in str(intent.params.get("explain_term") or "").split("+") if part]
            gear_note = ""
            if terms:
                shown = "、".join(f"「{part}」" for part in terms)
                gear_note = (
                    f"；text 先用一句话说明{shown}指什么，不要列举变体；"
                    f"替代动作的名字不要再带{shown}"
                )
            parts.append(
                f"排除动作={names}（换成同类替代，其余动作、标题和时长保持{gear_note}）"
            )

    # 正向处方；否定规则留给 SYSTEM_PROMPT
    if not strength:
        if "有氧" in modality and "HIIT" not in modality:
            parts.append("处方=时长与强度（如20分钟·RPE5）")
        elif "HIIT" in modality:
            parts.append("处方=做/歇秒数与轮数；动作从HIIT目录选")
        elif "灵活性" in modality:
            parts.append("处方=每侧秒数或次数；动作从灵活性目录选")
        elif intent.params.get("cardio"):
            parts.append("处方=时长与强度（如20分钟·RPE5）")

    if title and not intent.params.get("focus_exercises"):
        parts.append(f"标题={title}")

    return "；".join(parts)


def _format_stat_line(s: ExerciseStats) -> str:
    feel_str = f" 体感={s.last_feeling}" if s.last_feeling else ""
    outcome_str = f" 表现={s.last_outcome}" if s.last_outcome else ""
    if s.last_weight is not None:
        load = f"{s.last_weight}kg×{s.last_reps or '-'}"
        best = f"最好={s.best_weight}" if s.best_weight is not None else ""
    else:
        load = f"{s.last_reps or '-'}次/段"
        best = ""
    tail = f" {best} 趋势={s.trend}".strip() if best else f" 趋势={s.trend}"
    return f"{s.exercise_name}: 上次={load}{feel_str}{outcome_str}{tail}"


def _stats_match_modalities(name: str, want: list[str]) -> bool:
    if not want:
        return True
    have = modalities_of(name)
    return any(m in have for m in want)


def _stats_match_muscles(name: str, want: list[str]) -> bool:
    """按动作可作部位过滤；不要用「背」去扫整行字符串。"""
    if not want:
        return True
    roles = roles_of(name) or []
    return any(m in roles for m in want)


def assemble_memory(
    session: Session,
    intent: Intent,
    profile: Profile | None,
    top_n: int = 5,
    *,
    prefetch: bool = False,
) -> MemoryPack:
    """组装长期记忆。

    默认只带档案（prefetch=False）：相关训练/候选库由模型通过工具按需拉取，
    避免练背时把胸腿重量整表塞进提示词。
    prefetch=True 时仍可按部位/课型过滤后预取（兼容旧路径/评测）。
    """
    mods = session_modalities(intent)
    strength = is_strength_session(intent)
    profile_summary = build_profile_summary(profile, modalities=mods or None)
    derived: list[str] = []
    logs: list[str] = []
    candidates_block = ""

    if prefetch:
        muscle_filter = [m for m in (intent.muscles or []) if m != "全身"]
        if strength:
            stats = session.exec(select(ExerciseStats).limit(60)).all()
            for s in stats:
                if not _stats_match_modalities(s.exercise_name, ["抗阻"]):
                    continue
                if muscle_filter and not _stats_match_muscles(s.exercise_name, muscle_filter):
                    continue
                derived.append(_format_stat_line(s))
                if len(derived) >= 6:
                    break
            if muscle_filter:
                q = (
                    select(TrainingSetLog)
                    .where(TrainingSetLog.muscle.in_(muscle_filter))  # type: ignore[attr-defined]
                    .order_by(TrainingSetLog.id.desc())
                    .limit(top_n)
                )
                for r in session.exec(q).all():
                    feel = f" feel={r.feeling}" if r.feeling else ""
                    logs.append(
                        f"{r.exercise_name} set#{r.set_index} "
                        f"计划={r.target_weight}kg×{r.target_reps or '-'} "
                        f"实际={r.actual_weight or r.target_weight}kg×{r.actual_reps or '-'} "
                        f"done={r.completed}{feel}"
                    )
        else:
            want = mods or ["有氧"]
            for s in session.exec(select(ExerciseStats).limit(40)).all():
                if not _stats_match_modalities(s.exercise_name, want):
                    continue
                derived.append(_format_stat_line(s))
                if len(derived) >= 4:
                    break
            for r in session.exec(select(TrainingSetLog).order_by(TrainingSetLog.id.desc()).limit(30)).all():
                if not _stats_match_modalities(r.exercise_name, want):
                    continue
                feel = f" feel={r.feeling}" if r.feeling else ""
                logs.append(
                    f"{r.exercise_name} set#{r.set_index} "
                    f"计划={r.target_reps or '-'} "
                    f"实际={r.actual_reps or '-'} "
                    f"done={r.completed}{feel}"
                )
                if len(logs) >= top_n:
                    break

        injuries = list(profile.injuries) if profile else []
        avoid = list(getattr(profile, "avoid_exercises", None) or []) if profile else []
        exclude = list(intent.params.get("exclude_exercises") or []) + avoid
        focus = list(intent.params.get("focus_exercises") or [])
        equipment = list(intent.params.get("equipment") or []) or None
        boost = [
            s.exercise_name
            for s in session.exec(select(ExerciseStats).limit(60)).all()
            if (not muscle_filter or _stats_match_muscles(s.exercise_name, muscle_filter))
        ][:20]
        candidates = retrieve_candidates(
            muscles=intent.muscles or None,
            modalities=mods or None,
            equipment=equipment,
            injuries=injuries,
            exclude=exclude,
            focus=focus,
            boost_names=boost,
            limit=30,
        )
        have = {c["name"] for c in candidates}
        for name in focus:
            if name and name not in have:
                from app.exercises_catalog import EXERCISE_BY_NAME
                from app.taxonomy import canonicalize_exercise

                detail = EXERCISE_BY_NAME.get(canonicalize_exercise(name))
                if detail:
                    candidates.insert(0, detail)
                    have.add(detail["name"])
        candidates_block = format_candidates_block(candidates)

    pack = MemoryPack(
        profile_summary=profile_summary,
        derived_summaries=derived[:8],
        recent_logs=logs[:top_n],
        token_estimate=0,
        candidates_block=candidates_block,
    )
    pack.token_estimate = estimate_tokens(pack.as_prompt_block())

    budget = settings.memory_token_budget
    while pack.token_estimate > budget and pack.recent_logs:
        pack.recent_logs.pop()
        pack.token_estimate = estimate_tokens(pack.as_prompt_block())
    while pack.token_estimate > budget and len(pack.derived_summaries) > 1:
        pack.derived_summaries.pop()
        pack.token_estimate = estimate_tokens(pack.as_prompt_block())
    while pack.token_estimate > budget + 400 and pack.candidates_block:
        lines = pack.candidates_block.splitlines()
        if len(lines) <= 6:
            break
        pack.candidates_block = "\n".join(lines[:-3])
        pack.token_estimate = estimate_tokens(pack.as_prompt_block())

    return pack
