"""意图改写层：口语 → 结构化 Intent。

可插拔模型槽位（暂与主 LLM 共用；后续可单独接更轻量模型）。
规则解析始终作为 Fail-Closed 兜底与校验白名单。
"""

from __future__ import annotations

from typing import Any, Literal

from app.brain.llm import LLMClient, get_llm
from app.brain.memory import Intent, parse_intent
from app.config import settings
from app.exercises_catalog import find_exercises_in_text
from app.taxonomy import Muscle

ALLOWED_MUSCLES = {m.value for m in Muscle}
ALLOWED_EQUIPMENT = {"自重", "自由重量", "器械", "绳索"}
ALLOWED_EXPERTS = {"training", "profile", "general"}

INTENT_REWRITE_SYSTEM = """【INTENT_REWRITE】你是 Gym Coach 的意图改写器。把用户口语改写成严格 JSON（只输出 JSON）：
{
  "expert": "training|profile|general",
  "muscles": ["胸"|"背"|"肩"|"腿"|"臂"|"核心"|"全身"],
  "split": "上半身"|"下半身"|"推日"|"拉日"|null,
  "equipment": ["自重"|"自由重量"|"器械"|"绳索"]|null,
  "fatigue": false,
  "flexible": false,
  "rewrite": "一句话规范意图"
}
规则：
- 上半身→["胸","背","肩"]；下半身→["腿","核心"]；推日→["胸","肩","臂"]；拉日→["背","臂"]
- 出差/酒店/家里无器械→equipment=["自重"]；只有哑铃→["自由重量","自重"]
- 没劲/累/疲劳/感冒→fatigue=true
- 随便/搞搞→flexible=true
- 改画像/体重/目标→expert=profile
- muscles 只许用给定枚举；不确定则 muscles=[]，勿瞎猜危险动作
"""


def _sanitize_muscles(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for m in raw:
        if isinstance(m, str) and m in ALLOWED_MUSCLES and m not in out:
            out.append(m)
    return out


def _sanitize_equipment(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    out = [e for e in raw if isinstance(e, str) and e in ALLOWED_EQUIPMENT]
    return out or None


def intent_from_model_json(raw: dict[str, Any], user_text: str) -> Intent:
    expert = raw.get("expert") if raw.get("expert") in ALLOWED_EXPERTS else "general"
    muscles = _sanitize_muscles(raw.get("muscles"))
    params: dict[str, Any] = {"source": "llm"}
    split = raw.get("split")
    if isinstance(split, str) and split in ("上半身", "下半身", "推日", "拉日"):
        params["split"] = split
        # 若模型给了分化但漏了部位，按分化补全
        if not muscles:
            muscles = {
                "上半身": ["胸", "背", "肩"],
                "下半身": ["腿", "核心"],
                "推日": ["胸", "肩", "臂"],
                "拉日": ["背", "臂"],
            }[split]
    equipment = _sanitize_equipment(raw.get("equipment"))
    if equipment:
        params["equipment"] = equipment
    if raw.get("fatigue") is True:
        params["fatigue"] = True
        params["deload"] = True
    if raw.get("flexible") is True:
        params["flexible"] = True
    if isinstance(raw.get("rewrite"), str) and raw["rewrite"].strip():
        params["rewrite"] = raw["rewrite"].strip()

    # 模型判 training 但无部位时，若有器械/疲劳仍算训练意图
    if expert == "general" and (muscles or equipment or params.get("fatigue")):
        expert = "training"
    return Intent(expert=expert, muscles=muscles, raw=user_text, params=params)


def merge_intents(rules: Intent, model: Intent) -> Intent:
    """hybrid：模型优先补全模糊语义，规则补洞；疲劳/灵活取并集（更保守）。"""
    expert = model.expert if model.expert != "general" else rules.expert
    muscles = model.muscles or rules.muscles
    params: dict[str, Any] = {"source": "hybrid"}

    for key in ("split", "equipment", "rewrite"):
        if model.params.get(key) is not None:
            params[key] = model.params[key]
        elif rules.params.get(key) is not None:
            params[key] = rules.params[key]

    if model.params.get("fatigue") or rules.params.get("fatigue"):
        params["fatigue"] = True
        params["deload"] = True
    if model.params.get("flexible") or rules.params.get("flexible"):
        params["flexible"] = True

    if expert == "general" and (muscles or params.get("equipment") or params.get("fatigue")):
        expert = "training"
    return Intent(expert=expert, muscles=muscles, raw=rules.raw, params=params)


async def rewrite_intent(
    user_text: str,
    llm: LLMClient | None = None,
    mode: Literal["rules", "llm", "hybrid"] | None = None,
) -> Intent:
    """入口：按配置用规则 / 模型 / 混合改写意图。"""
    mode = mode or settings.intent_rewrite_mode  # type: ignore[assignment]
    rules = parse_intent(user_text)

    if mode == "rules":
        rules.params["source"] = "rules"
        return rules

    client = llm or get_intent_llm()
    if client is None:
        rules.params["source"] = "rules"
        return rules

    try:
        raw = await client.complete_json(INTENT_REWRITE_SYSTEM, user_text.strip())
        model_intent = intent_from_model_json(raw, user_text)
    except Exception:  # noqa: BLE001
        rules.params["source"] = "rules_fallback"
        return rules

    if mode == "llm":
        # 模型完全空时仍回落规则，避免静默丢意图
        if model_intent.expert == "general" and not model_intent.muscles and rules.expert != "general":
            rules.params["source"] = "rules_fallback"
            return rules
        return stamp_named_exercises(model_intent, rules)

    return stamp_named_exercises(merge_intents(rules, model_intent), rules)


_NAMED_TARGETS = (
    "胸",
    "背",
    "肩",
    "腿",
    "臀",
    "臂",
    "二头",
    "三头",
    "核心",
    "腹",
    "全身",
    "上半身",
    "下半身",
    "上肢",
    "下肢",
    "推日",
    "拉日",
)


_REVISION_CUES = (
    "只要",
    "只做",
    "只练",
    "主要做",
    "主要练",
    "就好了",
    "就这两个",
    "去掉",
    "不要",
    "换成",
    "改成",
    "加上",
    "加一个",
    "其他的",
    "下次再说",
    "保留",
    "剩下",
    "别加",
    "就这",
    "我自己看",
)


def user_named_target(text: str) -> bool:
    """点明了部位、分化，或动作库里的具体动作。没点明就不能替他决定练什么。"""
    if any(k in text for k in _NAMED_TARGETS):
        return True
    return bool(find_exercises_in_text(text))


def is_draft_revision(text: str) -> bool:
    """屏幕上已有草稿时，这句话是在改这一版，不是在重开一堂课。"""
    return any(k in text for k in _REVISION_CUES)


def needs_clarification(intent: Intent, has_draft: bool = False) -> bool:
    """欠拟合：像是要练，但没说练哪。画像类问题不拦。已有草稿的修改也不拦。"""
    if intent.expert == "profile":
        return False
    if user_named_target(intent.raw) or intent.params.get("focus_exercises"):
        return False
    if has_draft and is_draft_revision(intent.raw):
        return False
    vague = bool(
        intent.params.get("flexible")
        or intent.params.get("equipment")
        or intent.params.get("fatigue")
        or intent.expert == "training"
    )
    return vague


def build_clarification(intent: Intent) -> tuple[str, list[dict[str, str]]]:
    """反问 + 可选快捷说法。快捷说法写完整，下一轮才能直接排课。"""
    raw = intent.raw
    if any(k in raw for k in ("出差", "酒店", "旅馆", "民宿")):
        return (
            "出差我还不确定你在哪练、想练哪一块。你说一下，或点一个方向，我再排，不替你猜。",
            [
                {"label": "房间徒手", "prompt": "出差酒店房间，徒手练全身，20分钟"},
                {"label": "只有哑铃", "prompt": "酒店只有哑铃，练上半身"},
                {"label": "肩颈腰背活动", "prompt": "出差久坐，只做肩和核心舒展，15分钟"},
            ],
        )
    if intent.params.get("fatigue"):
        return (
            "你说状态一般，但我还不知道想动哪。说一下部位，我按不加重来排。",
            [
                {"label": "轻松练背", "prompt": "今天没劲，轻松练背，别加重"},
                {"label": "只做核心", "prompt": "今天累，只做核心"},
                {"label": "全身很短", "prompt": "今天疲劳，全身20分钟，降阶"},
            ],
        )
    return (
        "可以排，但还不知道练哪。说一下部位，或点一个方向。",
        [
            {"label": "练胸", "prompt": "今天练胸"},
            {"label": "练背", "prompt": "今天练背"},
            {"label": "练腿", "prompt": "今天练腿"},
            {"label": "全身", "prompt": "全身循环30分钟"},
        ],
    )


def stamp_named_exercises(intent: Intent, rules: Intent) -> Intent:
    """模型没认出动作名时，仍保留规则抽出的点名动作，避免被四个部位胶囊盖掉。"""
    focus = rules.params.get("focus_exercises")
    if not focus:
        return intent
    params = dict(intent.params)
    params["focus_exercises"] = list(focus)
    if rules.params.get("exclusive_focus"):
        params["exclusive_focus"] = True
    # 只合并用户/模型点名的部位，不用目录默认把硬拉收成「背」
    muscles = list(dict.fromkeys([*intent.muscles, *rules.muscles]))
    expert = intent.expert if intent.expert != "general" else "training"
    return Intent(expert=expert, muscles=muscles, raw=intent.raw or rules.raw, params=params)


def get_intent_llm() -> LLMClient | None:
    """意图改写专用模型槽。暂与主 LLM 相同；后续可独立配置更轻模型。"""
    provider = settings.intent_rewrite_provider
    if provider == "off":
        return None
    # same | mock | openai_compatible → 现阶段复用 get_llm()；换模型时只改这里/配置
    return get_llm()
