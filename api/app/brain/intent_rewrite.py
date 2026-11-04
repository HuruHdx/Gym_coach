"""意图改写：口语 → 结构化 Intent。

模型只做槽位提取与分流（agent / 课型 / 部位 / 点名 / 排除 / 是否已说侧重）。
是否反问（ready、tension）由 apply_coach_routing 按档案经验与长期目标决定。
规则解析始终作 Fail-Closed 兜底。
"""

from __future__ import annotations

from typing import Any, Literal

from app.brain.llm import TEMPERATURE_COPY, TEMPERATURE_STRUCTURED, LLMClient, get_llm
from app.brain.memory import Intent, parse_intent
from app.config import settings
from app.exercises_catalog import MODALITIES
from app.taxonomy import Muscle

ALLOWED_MUSCLES = {m.value for m in Muscle}
ALLOWED_EQUIPMENT = {"自重", "自由重量", "器械", "绳索"}
ALLOWED_AGENTS = {"coach_plan", "coach_chat", "nutrition"}
ALLOWED_TOPICS = {"plan", "qa", "chitchat"}
ALLOWED_DOMAINS = {"training", "nutrition", "general"}
# qa 上的回答合同。不是新的 topic，也不看学员档案。
ALLOWED_QA_KINDS = {"explain", "recall", "decide"}
# topic 决定分流。nutrition 不再是一级分类，只作为 domain。
TOPIC_TO_AGENT = {"plan": "coach_plan", "qa": "coach_chat", "chitchat": "coach_chat"}
ALLOWED_GOALS = {"增肌", "减脂", "力量", "塑形", "恢复"}
ALLOWED_MODALITIES = set(MODALITIES)
# 用户这句话和屏幕上那张计划的关系。确认不会自动采纳，也不会再出一张卡。
DRAFT_RELATIONS = {"confirm", "revise", "fresh"}
# 重排时，当前这堂的部位留不留。没说清就问，不默认换掉。
SESSION_TARGETS = {"keep", "switch", "ask"}
# Intent.expert 内部路由：training | chat | nutrition
AGENT_TO_EXPERT = {
    "coach_plan": "training",
    "coach_chat": "chat",
    "nutrition": "nutrition",
}
EXPERT_TO_AGENT = {v: k for k, v in AGENT_TO_EXPERT.items()}

INTENT_REWRITE_SYSTEM = """【INTENT_REWRITE】
你是 Gym Coach 的意图解析器（内部模块，只输出一行合法 JSON，不回复用户）。
只根据「短期记忆」「更早会话」和「当前输入」提取分类与槽位；不要判断要不要反问，也不要参考学员档案。

【一、主分类：topic 与 domain】
两条都必须输出，只允许使用枚举内的值。

1. topic（按 plan → qa → chitchat 顺序判定）：
- plan：本轮要产出、修改、重排或确认一份具体安排（训练课表或饮食餐单）。
  · 信息不足（只说要练、想出汗）或带约束（按上次重量、有点累随便练练）只要诉求是安排计划，都是 plan。
  · 面对短期记忆里的草稿表示接受/就用这套，仍属排课闭环，topic 填 plan（配合 draft_relation="confirm"）。
- qa：本轮要获取解释、动作要领、对比、训练/饮食建议，或查询个人数据/历史记录。
  · 询问规划建议但不是索要当堂课表（如问先练哪个部位好、一周练几次合适、某动作伤痛能不能做、练后酸痛是否正常）属于 qa，不是 plan。
  · 询问饮食怎么吃、热量计算、补剂对比或推荐属于 qa。
  · 查询个人数据（如某动作上次多重、近期练了几次、当前体重）属于 qa。
- chitchat：寒暄、道谢、纯情绪宣泄、无指代的简短附和，或明确表示不想练且不索要建议（既不要安排，也不问知识/数据）。

2. domain（只标识领域，不影响 topic）：
- training：动作技术、训练计划、运动恢复/伤痛、训练统计与身体数据。
- nutrition：饮食安排、热量、营养素、补剂。
- general：与训练和饮食无关的日常寒暄、情绪或闲聊。

3. qa_kind（仅 topic="qa" 时必填，否则 null。分类时不要参考学员档案）：
- explain：解释、要领、练哪里、怎么做、两类动作的区别。
- recall：查自己的次数、重量、记录、体重、目标。
- decide：做选择或给个人建议（先练哪个、一周几次、加不加、吃多少、能不能做）。要的是决定，不是当堂课表。

【二、草稿关系：draft_relation 与 session_target】
短期记忆是今天到上一轮为止的对话，教练给出的计划草稿嵌在其中（「更早会话」仅用于理解昨天/上次的指代，不算今日草稿）。
- 当短期记忆里没有草稿，或本句是在问知识/查数据/闲聊/排饮食时：draft_relation 和 session_target 均填 null。
- 当短期记忆里已有草稿，且用户本句在对这张草稿表态时（此时 topic="plan"）：
  1) draft_relation：
     - "confirm"：接受当前这张计划，不再增删改内容。
     - "revise"：保留当前计划框架，只局部修改其中点到的项（如换掉某个没器械的动作、删一项、改强度/组数）。
     - "fresh"：不要当前这套动作安排，要求重新排一版。
  2) session_target（仅当 draft_relation="fresh" 时填写，其余一律填 null）：
     - "keep"：部位不变，只换一套动作或方案。
     - "switch"：明确点了新部位，或明确说不练当前部位了。
     - "ask"：只说换个计划/重排，未说明当前部位留还是换（不要因为「换计划」就推断放弃当前部位）。

【三、槽位提取规则】
只填用户本句或上文指代里明确出现的内容，未提及填 null（列表填 []），不要脑补：
- goal：本句明确点名的目标（"增肌"|"减脂"|"力量"|"塑形"|"恢复"）。否定句（如「不想上大重量」）填 null。
- modality：["抗阻"|"有氧"|"HIIT"|"灵活性"]|null。明确练某部位或力量动作填 ["抗阻"]；只说「出出汗」「动一动」未定课型填 null。
- muscles：["胸"|"背"|"肩"|"腿"|"臂"|"核心"|"全身"]。
  · 点名了部位，或提到了具体动作（如深蹲→["腿"]、卧推→["胸"]、下拉/划船→["背"]）时填入对应部位。
  · 纯有氧或 HIIT 未点部位填 ["全身"] 或 []。
  · 重排（draft_relation="fresh"）但本句未重新点名部位时保持 []，不要把上一张草稿的部位抄进来。
- split："上半身"|"下半身"|"推日"|"拉日"|null。
- equipment：["自重"|"自由重量"|"器械"|"绳索"]|null。
- fatigue：表达累、没劲、状态差时为 true，否则 false。
- minutes：本句提到的分钟数（整数），否则 null。
- intensity：明确要求低强度/恢复/轻松填 "low"；明确要求高强度/暴汗/冲刺填 "high"；否则 null。
- focus_exercises：用户点名要练或所询问的具体动作名列表（保留用户说法），无则 null。解剖部位/肌群细分（如股四头肌、上胸、后链）绝不要写进这里。
- exclude_exercises：用户说没有、用不了、去掉、换掉的动作或器械列表，无则 null。被排除项不要同时放进 focus_exercises。
- exclusive_focus：明确表示「只做这几个动作、不要其他动作」时为 true，否则 false。
- has_focus_detail：已说出比大部位更细的练法时为 true（包括肌群细分如股四/后链/上胸/宽度/厚度、组次风格如大重量低次数/泵感、器械打法如自由深蹲为主）；只说大部位（如「练腿」「练胸」）为 false。
- rewrite：一句话客观复述本轮诉求。confirm 写成「确认使用当前计划」；ask 写成「对当前计划不满意，部位去留未说明」；keep 写成「部位不变，只换一套动作」；switch 写明换成哪个部位；revise 写明改哪一项（被排除的动作不要写成要练它）。

【四、输出格式】
严格只输出以下单行 JSON，不要代码块或多余文字：
{"topic":"plan|qa|chitchat","domain":"training|nutrition|general","qa_kind":"explain"|"recall"|"decide"|null,"goal":"增肌"|"减脂"|"力量"|"塑形"|"恢复"|null,"modality":["抗阻"|"有氧"|"HIIT"|"灵活性"]|null,"muscles":["胸"|"背"|"肩"|"腿"|"臂"|"核心"|"全身"],"split":"上半身"|"下半身"|"推日"|"拉日"|null,"equipment":["自重"|"自由重量"|"器械"|"绳索"]|null,"fatigue":false,"minutes":null,"intensity":"low"|"high"|null,"focus_exercises":["深蹲"]|null,"exclude_exercises":["划船机"]|null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":"confirm"|"revise"|"fresh"|null,"session_target":"keep"|"switch"|"ask"|null,"rewrite":"一句话客观描述本轮诉求"}

【五、示例】
- 「今天随便出出汗」→ {"topic":"plan","domain":"training","goal":null,"modality":null,"muscles":[],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"想运动出汗，课型与部位未说明"}
- 「今天练腿，主攻股四头肌」→ {"topic":"plan","domain":"training","goal":null,"modality":["抗阻"],"muscles":["腿"],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":true,"rewrite":"腿部抗阻，主攻股四头肌"}
- 「这次就做深蹲和硬拉两个动作，别的不用排」→ {"topic":"plan","domain":"training","goal":null,"modality":["抗阻"],"muscles":["腿"],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":["深蹲","硬拉"],"exclude_exercises":null,"exclusive_focus":true,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"只安排深蹲与硬拉"}
- 「帮我定一份一日三餐减脂食谱」→ {"topic":"plan","domain":"nutrition","goal":"减脂","modality":null,"muscles":[],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"安排减脂饮食计划"}
- 短期记忆已有草稿，用户：「健身房没划船机，把这个换掉」→ {"topic":"plan","domain":"training","goal":null,"modality":null,"muscles":[],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":["划船机"],"exclusive_focus":false,"has_focus_detail":false,"draft_relation":"revise","session_target":null,"rewrite":"在当前计划里替换不可用的划船机"}
- 短期记忆已有草稿，用户：「行，就按这套来」→ {"topic":"plan","domain":"training","goal":null,"modality":null,"muscles":[],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":"confirm","session_target":null,"rewrite":"确认使用当前计划"}
- 短期记忆已有腿部草稿，用户：「这套不行，换个计划」→ {"topic":"plan","domain":"training","goal":null,"modality":null,"muscles":[],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":"fresh","session_target":"ask","rewrite":"对当前计划不满意，部位去留未说明"}
- 短期记忆已有腿部草稿，用户：「还是练腿，但把动作全换一套」→ {"topic":"plan","domain":"training","goal":null,"modality":null,"muscles":[],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":"fresh","session_target":"keep","rewrite":"部位不变，只换一套动作"}
- 短期记忆已有腿部草稿，用户：「算了今天改练背」→ {"topic":"plan","domain":"training","goal":null,"modality":["抗阻"],"muscles":["背"],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":"fresh","session_target":"switch","rewrite":"换成背部训练"}
- 「深蹲练哪里」→ {"topic":"qa","qa_kind":"explain","domain":"training","goal":null,"modality":null,"muscles":["腿"],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":["深蹲"],"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"询问深蹲练到的部位"}
- 「周末先练肩还是先练手臂好？」→ {"topic":"qa","qa_kind":"decide","domain":"training","goal":null,"modality":null,"muscles":["肩","臂"],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"咨询先练肩还是先练臂的建议"}
- 「明天练胸还是练背好」→ {"topic":"qa","qa_kind":"decide","domain":"training","goal":null,"modality":null,"muscles":["胸","背"],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"咨询下次先练胸还是先练背"}
- 「这周还想加练一天行不行」→ {"topic":"qa","qa_kind":"decide","domain":"training","goal":null,"modality":null,"muscles":[],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"咨询能否在本周增加一次训练"}
- 「膝盖有点弹响还能做深蹲吗」→ {"topic":"qa","qa_kind":"decide","domain":"training","goal":null,"modality":null,"muscles":["腿"],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":["深蹲"],"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"咨询膝盖弹响能否做深蹲"}
- 「我上次深蹲做到多重」→ {"topic":"qa","qa_kind":"recall","domain":"training","goal":null,"modality":null,"muscles":["腿"],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":["深蹲"],"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"查询上次深蹲的训练重量"}
- 「训练后喝乳清蛋白还是吃正餐好」→ {"topic":"qa","qa_kind":"decide","domain":"nutrition","goal":null,"modality":null,"muscles":[],"split":null,"equipment":null,"fatigue":false,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"咨询训后补充乳清蛋白与正餐的选择"}
- 「今天加班太累了，不想去健身房了」→ {"topic":"chitchat","domain":"general","goal":null,"modality":null,"muscles":[],"split":null,"equipment":null,"fatigue":true,"minutes":null,"intensity":null,"focus_exercises":null,"exclude_exercises":null,"exclusive_focus":false,"has_focus_detail":false,"draft_relation":null,"session_target":null,"rewrite":"表达疲惫不想训练"}
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


def _sanitize_modalities(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return None
    out: list[str] = []
    for m in raw:
        if isinstance(m, str) and m in ALLOWED_MODALITIES and m not in out:
            out.append(m)
    return out or None


def _sanitize_goal(raw: Any) -> str | None:
    if isinstance(raw, str) and raw in ALLOWED_GOALS:
        return raw
    return None


def _normalize_agent(raw: dict[str, Any]) -> str:
    agent = raw.get("agent")
    if isinstance(agent, str) and agent in ALLOWED_AGENTS:
        return agent
    # 兼容旧字段 expert
    expert = raw.get("expert")
    if expert == "training":
        return "coach_plan"
    if expert in ("chat", "general", "profile"):
        return "coach_chat"
    if expert == "nutrition":
        return "nutrition"
    return "coach_chat"


def _legacy_style_to_modality(style: Any, cardio: bool) -> list[str] | None:
    """兼容旧 session_style / cardio 字段。"""
    if style == "cardio" or cardio:
        return ["有氧"]
    if style == "strength":
        return ["抗阻"]
    if style == "mixed":
        return ["抗阻", "有氧"]
    return None


def _plan_ready(muscles: list[str], params: dict[str, Any], raw_ready: Any | object = ...) -> bool:
    if raw_ready is not ... and raw_ready is not None:
        # 显式 false 仍可被结构化信号抬升
        explicit = bool(raw_ready)
    else:
        explicit = False
    signals = bool(
        muscles
        or params.get("focus_exercises")
        or params.get("modality")
        or params.get("cardio")
        or params.get("split")
        or params.get("goal")
    )
    return explicit or signals


def intent_from_model_json(raw: dict[str, Any], user_text: str) -> Intent:
    agent = _normalize_agent(raw)
    expert = AGENT_TO_EXPERT[agent]
    muscles = _sanitize_muscles(raw.get("muscles"))
    params: dict[str, Any] = {"source": "llm", "agent": agent}
    topic = raw.get("topic")
    if isinstance(topic, str) and topic in ALLOWED_TOPICS:
        params["topic"] = topic
        agent = TOPIC_TO_AGENT[topic]
        params["agent"] = agent
        expert = AGENT_TO_EXPERT[agent]
    domain = raw.get("domain")
    if isinstance(domain, str) and domain in ALLOWED_DOMAINS:
        params["domain"] = domain
    qa_kind = raw.get("qa_kind")
    if params.get("topic") == "qa" and isinstance(qa_kind, str) and qa_kind in ALLOWED_QA_KINDS:
        params["qa_kind"] = qa_kind

    goal = _sanitize_goal(raw.get("goal"))
    if goal:
        params["goal"] = goal

    modality = _sanitize_modalities(raw.get("modality"))
    if not modality:
        modality = _legacy_style_to_modality(raw.get("session_style"), bool(raw.get("cardio")))
    if modality:
        params["modality"] = modality
        if "有氧" in modality and "抗阻" not in modality and "HIIT" not in modality:
            params["cardio"] = True
            params["session_style"] = "cardio"
            if not muscles:
                muscles = ["全身"]
        elif "HIIT" in modality and not muscles:
            muscles = ["全身"]
        elif "灵活性" in modality and "抗阻" not in modality and not muscles:
            pass  # 拉伸可不点部位
        elif "抗阻" in modality and not muscles:
            pass

    split = raw.get("split")
    if isinstance(split, str) and split in ("上半身", "下半身", "推日", "拉日"):
        params["split"] = split
        if not muscles:
            muscles = {
                "上半身": ["胸", "背", "肩"],
                "下半身": ["腿", "核心"],
                "推日": ["胸", "肩", "臂"],
                "拉日": ["背", "臂"],
            }[split]
        if not modality:
            params["modality"] = ["抗阻"]

    # 仍接受旧 session_style（无 modality 时）
    style = raw.get("session_style")
    if style in ("strength", "cardio", "mixed") and "modality" not in params:
        params["session_style"] = style
        if style == "cardio":
            params["cardio"] = True
            params["modality"] = ["有氧"]
            if not muscles:
                muscles = ["全身"]
        elif style == "strength":
            params["modality"] = ["抗阻"]
        else:
            params["modality"] = ["抗阻", "有氧"]

    equipment = _sanitize_equipment(raw.get("equipment"))
    if equipment:
        params["equipment"] = equipment
    if raw.get("fatigue") is True:
        params["fatigue"] = True
        params["deload"] = True
    if raw.get("flexible") is True:
        params["flexible"] = True
    minutes = raw.get("minutes")
    if isinstance(minutes, (int, float)) and 5 <= float(minutes) <= 180:
        params["session_minutes"] = int(minutes)
    if isinstance(raw.get("rewrite"), str) and raw["rewrite"].strip():
        params["rewrite"] = raw["rewrite"].strip()

    intensity = raw.get("intensity")
    if intensity in ("low", "high"):
        params["intensity"] = intensity

    from app.exercises_catalog import looks_like_exercise_name

    # 模型给出的点名；过滤解剖标签。简称如「深蹲」可过（不像「股四头肌」）。
    focus = [n for n in _sanitize_name_list(raw.get("focus_exercises")) if looks_like_exercise_name(n)]
    exclude = _sanitize_name_list(raw.get("exclude_exercises"))
    if focus:
        params["focus_exercises"] = focus
    if exclude:
        params["exclude_exercises"] = exclude
        if params.get("focus_exercises"):
            params["focus_exercises"] = [n for n in params["focus_exercises"] if n not in exclude]
            if not params["focus_exercises"]:
                params.pop("focus_exercises", None)
    if raw.get("exclusive_focus") is True and params.get("focus_exercises"):
        params["exclusive_focus"] = True
    if raw.get("has_focus_detail") is True:
        params["has_focus_detail"] = True
    relation = raw.get("draft_relation")
    if relation in DRAFT_RELATIONS:
        params["draft_relation"] = relation
    session_target = raw.get("session_target")
    if session_target in SESSION_TARGETS:
        params["session_target"] = session_target

    # ready / tension 不采用模型输出，交给 apply_coach_routing
    if agent == "coach_plan":
        params["ready"] = _plan_ready(muscles, params)
    else:
        params["ready"] = True

    return apply_draft_relation(Intent(expert=expert, muscles=muscles, raw=user_text, params=params))


def _sanitize_name_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            if name and name not in out:
                out.append(name)
    return out[:12]


def _sanitize_tension(raw: Any) -> dict[str, Any] | None:
    """意图改写只保留 kind；话术留给 CLARIFY。若传入完整 question/suggestions（CLARIFY 输出）则保留。"""
    if not isinstance(raw, dict) or not raw.get("has_tension"):
        return None
    kind = raw.get("kind") if isinstance(raw.get("kind"), str) else "general"
    question = raw.get("question")
    suggestions_in = raw.get("suggestions")
    suggestions: list[dict[str, str]] = []
    if isinstance(suggestions_in, list):
        for item in suggestions_in[:4]:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            prompt = item.get("prompt")
            if isinstance(label, str) and isinstance(prompt, str) and label.strip() and prompt.strip():
                suggestions.append({"label": label.strip()[:20], "prompt": prompt.strip()[:80]})
    # 意图分流带来的半成品：只标 kind，话术清空
    if not (isinstance(question, str) and question.strip() and len(suggestions) >= 2):
        return {
            "has_tension": True,
            "kind": kind[:32],
            "question": "",
            "suggestions": [],
        }
    return {
        "has_tension": True,
        "kind": kind[:32],
        "question": _scrub_level_address(question.strip())[:240],
        "suggestions": suggestions,
    }


def merge_intents(rules: Intent, model: Intent) -> Intent:
    """hybrid：agent 以模型为主，规则补洞；计划未就绪时规则能标 modality/部位则抬升 ready。"""
    model_agent = model.params.get("agent") or EXPERT_TO_AGENT.get(model.expert, "coach_chat")
    rules_agent = rules.params.get("agent") or EXPERT_TO_AGENT.get(rules.expert, "coach_chat")

    # 规则明确认出排课目标时，不要被模型误判成闲聊
    if rules_agent == "coach_plan" and (
        rules.muscles
        or rules.params.get("focus_exercises")
        or rules.params.get("cardio")
        or rules.params.get("modality")
        or rules.params.get("goal")
    ):
        agent = "coach_plan"
    elif model_agent in ALLOWED_AGENTS:
        agent = model_agent
    else:
        agent = rules_agent

    expert = AGENT_TO_EXPERT[agent]
    muscles = model.muscles or rules.muscles
    params: dict[str, Any] = {"source": "hybrid", "agent": agent}

    for key in (
        "split",
        "equipment",
        "rewrite",
        "session_style",
        "session_minutes",
        "goal",
        "modality",
        "intensity",
        "focus_exercises",
        "exclude_exercises",
        "has_focus_detail",
        "draft_relation",
        "session_target",
    ):
        if model.params.get(key) is not None:
            params[key] = model.params[key]
        elif rules.params.get(key) is not None:
            params[key] = rules.params[key]

    if model.params.get("exclusive_focus") or rules.params.get("exclusive_focus"):
        if params.get("focus_exercises"):
            params["exclusive_focus"] = True

    if model.params.get("fatigue") or rules.params.get("fatigue"):
        params["fatigue"] = True
        params["deload"] = True
    if model.params.get("flexible") or rules.params.get("flexible"):
        params["flexible"] = True

    modality = params.get("modality")
    if not modality and (model.params.get("cardio") or rules.params.get("cardio")):
        modality = ["有氧"]
        params["modality"] = modality
    if modality:
        if "有氧" in modality and "抗阻" not in modality:
            params["cardio"] = True
            params["session_style"] = params.get("session_style") or "cardio"
            named_part = any(k in (rules.raw or "") for k in ("胸", "背", "肩", "腿", "臂", "核心", "腹"))
            if not named_part and ("有氧" in modality or "HIIT" in modality):
                muscles = ["全身"]
                agent = "coach_plan"
                expert = "training"
                params["agent"] = agent
    elif model.params.get("cardio") or rules.params.get("cardio"):
        params["cardio"] = True
        params["session_style"] = params.get("session_style") or "cardio"
        params["modality"] = ["有氧"]
        named_part = any(k in (rules.raw or "") for k in ("胸", "背", "肩", "腿", "臂", "核心", "腹"))
        if not named_part:
            muscles = ["全身"]
            agent = "coach_plan"
            expert = "training"
            params["agent"] = agent

    topic = model.params.get("topic")
    if isinstance(topic, str) and topic in ALLOWED_TOPICS:
        params["topic"] = topic
        agent = TOPIC_TO_AGENT[topic]
        expert = AGENT_TO_EXPERT[agent]
        params["agent"] = agent
    domain = model.params.get("domain")
    if isinstance(domain, str) and domain in ALLOWED_DOMAINS:
        params["domain"] = domain
    qa_kind = model.params.get("qa_kind")
    if params.get("topic") == "qa" and qa_kind in ALLOWED_QA_KINDS:
        params["qa_kind"] = qa_kind

    if agent == "coach_plan":
        ready = bool(model.params.get("ready")) if "ready" in model.params else False
        if _plan_ready(muscles, params):
            ready = True
        if rules.params.get("ready") is False and not _plan_ready(muscles, params):
            ready = False
        params["ready"] = ready
    else:
        params["ready"] = True

    return apply_draft_relation(
        Intent(expert=expert, muscles=muscles, raw=rules.raw or model.raw, params=params)
    )


async def rewrite_intent(
    user_text: str,
    llm: LLMClient | None = None,
    mode: Literal["rules", "llm", "hybrid"] | None = None,
    profile: Any | None = None,
    history: list[Any] | None = None,
    context: str | None = None,
    draft_title: str | None = None,
) -> Intent:
    """入口：按配置用规则 / 模型 / 混合改写意图。context 是对话，不含档案。"""
    from app.brain.memory import format_dialogue_for_prompt

    mode = mode or settings.intent_rewrite_mode  # type: ignore[assignment]
    rules = parse_intent(user_text)
    rules = _stamp_agent_fields(rules)

    if mode == "rules":
        rules.params["source"] = "rules"
        return _routed(rules, profile, history, draft_title, context)

    client = llm or get_intent_llm()
    if client is None:
        rules.params["source"] = "rules"
        return _routed(rules, profile, history, draft_title, context)

    dialogue = "" if context else format_dialogue_for_prompt(history)
    # 档案只交给路由层，不进意图模型
    user_payload = context or (
        f"{dialogue}"
        f"用户本句：{user_text.strip()}\n"
    )
    try:
        raw = await client.complete_json(
            INTENT_REWRITE_SYSTEM,
            user_payload,
            temperature=TEMPERATURE_STRUCTURED,
        )
        model_intent = intent_from_model_json(raw, user_text)
    except Exception:  # noqa: BLE001
        rules.params["source"] = "rules_fallback"
        return _routed(rules, profile, history, draft_title, context)

    if mode == "llm":
        stamped = _stamp_agent_fields(model_intent)
        params = dict(stamped.params)
        params["source"] = "llm"
        return _routed(
            Intent(
                expert=stamped.expert,
                muscles=list(stamped.muscles),
                raw=stamped.raw,
                params=params,
            ),
            profile,
            history,
            draft_title,
            context,
        )

    return _routed(
        _finalize(merge_intents(rules, model_intent), rules),
        profile,
        history,
        draft_title,
        context,
    )


def _routed(
    intent: Intent,
    profile: Any | None,
    history: list[Any] | None,
    draft_title: str | None = None,
    memory_text: str | None = None,
) -> Intent:
    """教练路由之后，再用草案关系盖住最终分流。confirm 不能被「练」字拉回去排课。"""
    routed = apply_draft_relation(apply_coach_routing(intent, profile, history))
    return apply_session_target(routed, draft_title, history, memory_text)


def apply_draft_relation(intent: Intent) -> Intent:
    """草案关系是结构，不是某几句口头禅。

    confirm：用户接受当前这张卡。没点采纳按钮之前，不自动开始，也不再出一张卡。
    revise / fresh：仍走排课。fresh 是放弃当前卡重排，revise 是改当前卡。
    """
    relation = (intent.params or {}).get("draft_relation")
    if relation not in DRAFT_RELATIONS:
        return intent
    params = dict(intent.params or {})
    if relation == "confirm":
        params["agent"] = "coach_chat"
        params["adopt_hint"] = True
        params["ready"] = True
        params.pop("tension", None)
        return Intent(expert="chat", muscles=[], raw=intent.raw, params=params)
    params["agent"] = "coach_plan"
    params.pop("adopt_hint", None)
    if "ready" not in params:
        params["ready"] = True
    return Intent(
        expert="training",
        muscles=list(intent.muscles),
        raw=intent.raw,
        params=params,
    )


_TITLE_MUSCLES = ("胸", "背", "肩", "腿", "臂", "核心", "全身")


def muscles_from_draft_title(title: str | None) -> list[str]:
    if not title:
        return []
    return [muscle for muscle in _TITLE_MUSCLES if muscle in title]


def _history_text(history: list[Any] | None, roles: set[str]) -> str:
    parts: list[str] = []
    for turn in history or []:
        role = turn.get("role") if isinstance(turn, dict) else getattr(turn, "role", "")
        if role not in roles:
            continue
        text = turn.get("text") if isinstance(turn, dict) else getattr(turn, "text", "")
        if text:
            parts.append(str(text))
    return "\n".join(parts)


def _rejects_open_target(text: str, muscles: list[str]) -> bool:
    return any(f"不练{muscle}" in text or f"别练{muscle}" in text or f"不要{muscle}" in text for muscle in muscles)


def _switches_away(intent: Intent, open_muscles: list[str]) -> bool:
    named = [muscle for muscle in intent.muscles if muscle != "全身"]
    if named and set(named) != set(open_muscles) and not set(named).issubset(open_muscles):
        return True
    return _rejects_open_target(intent.raw or "", open_muscles)


def _session_question(intent: Intent, open_muscles: list[str]) -> Intent:
    params = dict(intent.params or {})
    params["session_target"] = "ask"
    params["agent"] = "coach_plan"
    params["ready"] = False
    params.pop("adopt_hint", None)
    if open_muscles:
        params["open_target"] = "+".join(open_muscles)
    params["tension"] = {
        "has_tension": True,
        "kind": "session",
        "muscle": open_muscles[0] if len(open_muscles) == 1 else "",
        "question": "",
        "suggestions": [],
    }
    return Intent(expert="training", muscles=[], raw=intent.raw, params=params)


def apply_session_target(
    intent: Intent,
    draft_title: str | None,
    history: list[Any] | None = None,
    memory_text: str | None = None,
) -> Intent:
    """重排时先定部位去留。没说换部位，就不能当成不练上一张的部位。

    keep：沿用上一张的部位；上一张或更早对话里已经写过的侧重也留下，不再追问。
    ask：只问一次，先给「按当前部位再排一版」。
    switch：用户点了别的部位，或明确说不练当前部位。
    """
    params = dict(intent.params or {})
    relation = params.get("draft_relation")
    target = params.get("session_target")
    if relation == "confirm" or params.get("adopt_hint"):
        return intent
    open_muscles = muscles_from_draft_title(draft_title)
    if relation != "fresh" and target not in SESSION_TARGETS:
        return intent
    if not open_muscles:
        return intent
    if target not in SESSION_TARGETS:
        if _switches_away(intent, open_muscles):
            target = "switch"
        elif intent.muscles and set(intent.muscles) == set(open_muscles):
            target = "keep"
        else:
            target = "ask"
    if target == "switch" and not _switches_away(intent, open_muscles):
        target = "ask"
    if target == "ask":
        return _session_question(intent, open_muscles)
    if target == "keep":
        muscles = list(intent.muscles) or list(open_muscles)
        prior = "\n".join(
            part
            for part in (
                _history_text(history, {"user", "human", "assistant"}),
                memory_text or "",
            )
            if part
        )
        if params.get("has_focus_detail") or has_focus_detail(prior) or has_focus_detail(intent.raw or ""):
            params["has_focus_detail"] = True
        params["session_target"] = "keep"
        params["open_target"] = "+".join(open_muscles)
        params["agent"] = "coach_plan"
        params["ready"] = True
        params.pop("tension", None)
        params.pop("adopt_hint", None)
        return Intent(expert="training", muscles=muscles, raw=intent.raw, params=params)
    params["session_target"] = "switch"
    return Intent(expert=intent.expert, muscles=list(intent.muscles), raw=intent.raw, params=params)


def _stamp_agent_fields(intent: Intent) -> Intent:
    params = dict(intent.params or {})
    if intent.expert == "training":
        params["agent"] = "coach_plan"
        if "ready" not in params:
            params["ready"] = _plan_ready(list(intent.muscles), params)
    elif intent.expert == "nutrition":
        params["agent"] = "nutrition"
        params["ready"] = True
    elif intent.expert == "profile":
        # 画像改在「我的」，聊天里当闲聊引导
        return Intent(
            expert="chat",
            muscles=[],
            raw=intent.raw,
            params={**params, "agent": "coach_chat", "ready": True, "rewrite": "引导去我的页改资料"},
        )
    else:
        params["agent"] = "coach_chat"
        params["ready"] = True
    return Intent(
        expert=intent.expert if intent.expert != "general" else "chat",
        muscles=list(intent.muscles),
        raw=intent.raw,
        params=params,
    )


def _finalize(intent: Intent, rules: Intent) -> Intent:
    intent = _stamp_agent_fields(intent)
    modality = intent.params.get("modality") or []
    cardioish = bool(rules.params.get("cardio") or intent.params.get("cardio") or "有氧" in modality)
    if cardioish and intent.params.get("agent") == "coach_plan":
        params = dict(intent.params)
        params["cardio"] = True
        params["session_style"] = params.get("session_style") or "cardio"
        if not params.get("modality"):
            params["modality"] = list(rules.params.get("modality") or ["有氧"])
        params["ready"] = True
        named_part = any(k in (intent.raw or "") for k in ("胸", "背", "肩", "腿", "臂", "核心", "腹"))
        # 纯有氧/HIIT 不点部位 → 全身；点了部位则保留
        if "抗阻" in (params.get("modality") or []) and named_part:
            muscles = list(intent.muscles)
        else:
            muscles = list(intent.muscles) if named_part and intent.muscles else ["全身"]
        return Intent(expert="training", muscles=muscles, raw=intent.raw, params=params)
    return intent


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
    "换掉",
    "替掉",
    "替代",
    "换一个",
    "换个",
    "用不了",
    "没这个",
    "没有这",
    "也没有",
    "都没有",
    "没有",
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
    """点明了部位或分化（具体动作点名交给意图模型）。"""
    return any(k in text for k in _NAMED_TARGETS)


def is_draft_revision(text: str, params: dict[str, Any] | None = None) -> bool:
    """屏幕上已有草稿时，这句话是在改这一版，不是在重开一堂课。"""
    if params and params.get("exclude_exercises"):
        return True
    if params and params.get("draft_relation") in ("confirm", "fresh"):
        return False
    return any(k in text for k in _REVISION_CUES)


_INTENSITY_CUES = (
    "高强度",
    "低强度",
    "暴汗",
    "爆汗",
    "冲刺",
    "恢复",
    "排酸",
    "慢走",
    "轻松有氧",
    "拉满",
    "RPE",
    "rpe",
    "练心肺",
    "保肌肉",
    "不影响增肌",
    "大重量",
    "低次数",
    "高次数",
    "泵感",
    "力量为主",
    "增肌训练",
)

# 大部位下的细化侧重 / 器械风格：有这些就不再当成「只说练腿」
_FOCUS_DETAIL_CUES = (
    "股四",
    "前侧",
    "后链",
    "腘绳",
    "股二",
    "臀",
    "上胸",
    "中缝",
    "下胸",
    "宽度",
    "厚度",
    "不够宽",
    "不够厚",
    "要宽",
    "偏厚",
    "宽一点",
    "厚一点",
    "背阔",
    "中背",
    "侧重",
    "主攻",
    "主力",
    "复合",
    "孤立",
    "自由深蹲",
    "自由重量",
    "器械为主",
    "腿举",
    "哈克",
    "前蹲",
    "硬拉为主",
    "下拉",
    "划船为主",
)


def has_intensity_cue(text: str) -> bool:
    return any(k in text for k in _INTENSITY_CUES)


def has_focus_detail(text: str) -> bool:
    return any(k in text for k in _FOCUS_DETAIL_CUES)


def _is_blank_plan(intent: Intent) -> bool:
    """确认要练但完全不知道练什么。"""
    if intent.params.get("focus_exercises"):
        return False
    if intent.params.get("split"):
        return False
    if intent.muscles:
        return False
    mods = intent.params.get("modality") or []
    if mods or intent.params.get("cardio"):
        return False
    if intent.params.get("goal") and intent.params.get("goal_source") != "profile":
        # 本句点了减脂/增肌等也算有方向
        return False
    return True


def _broad_muscle_only(intent: Intent, params: dict[str, Any] | None = None) -> bool:
    """大类目部位已清，但未点动作、未说侧重。"""
    data = intent.params if params is None else params
    if data.get("focus_exercises") or data.get("has_focus_detail"):
        return False
    raw = intent.raw or ""
    if has_intensity_cue(raw) or has_focus_detail(raw):
        return False
    muscles = [m for m in (intent.muscles or []) if m != "全身"]
    return bool(muscles) and not intent.params.get("split")


def _vague_cardio(intent: Intent) -> bool:
    mods = intent.params.get("modality") or []
    cardio = bool(intent.params.get("cardio") or ("有氧" in mods and "抗阻" not in mods))
    if not cardio:
        return False
    if intent.params.get("focus_exercises"):
        return False
    if has_intensity_cue(intent.raw or ""):
        return False
    if intent.params.get("intensity") in ("low", "high"):
        return False
    return True


def _ready_enough_to_plan(intent: Intent, params: dict[str, Any]) -> bool:
    """用户本句已足够排课：点名动作、强度、或部位/器械侧重。"""
    raw = intent.raw or ""
    if params.get("focus_exercises") or params.get("has_focus_detail"):
        return True
    if has_intensity_cue(raw) or has_focus_detail(raw):
        return True
    if params.get("intensity") in ("low", "high"):
        return True
    if params.get("split") or params.get("equipment"):
        return True
    return False


_KNOWLEDGE_CUES = (
    "什么是",
    "怎么做",
    "怎么避免",
    "为什么",
    "如何",
    "怎样",
    "能不能练",
    "要领",
    "该怎么练",
    "应该怎么练",
    # 排课线程里的比较/选择问句，不是在改课
    "区别",
    "有什么不同",
    "有啥不同",
    "哪个好",
    "哪个更",
    "更适合",
    "能不能替代",
    "可以替代",
    "有什么用",
    "对比",
)
_PLAN_THREAD_CUES = ("练背", "练胸", "练腿", "练肩", "练臂", "练核心", "今天要练", "主攻", "排一堂", "安排")
_THREAD_MUSCLES = (
    ("练背", "背"),
    ("背部", "背"),
    ("练胸", "胸"),
    ("练腿", "腿"),
    ("练肩", "肩"),
    ("练臂", "臂"),
    ("练核心", "核心"),
)


def _history_user_text(history: list[Any] | None) -> str:
    parts: list[str] = []
    for turn in history or []:
        role = turn.get("role") if isinstance(turn, dict) else getattr(turn, "role", "")
        if role not in ("user", "human"):
            continue
        text = turn.get("text") if isinstance(turn, dict) else getattr(turn, "text", "")
        if text:
            parts.append(str(text))
    return "\n".join(parts)


def _stick_to_open_plan(intent: Intent, history: list[Any] | None) -> Intent:
    """排课对话里的后续句继续走排课。知识问答、确认当前卡仍留在 chat。"""
    if (intent.params or {}).get("draft_relation") == "confirm":
        return intent
    raw = intent.raw or ""
    if any(k in raw for k in _KNOWLEDGE_CUES):
        # 模型若把比较问句判成排课，规则层拉回问答。改稿（revise/fresh）仍留给排课。
        if (intent.params or {}).get("draft_relation") in ("revise", "fresh"):
            return intent
        params = dict(intent.params or {})
        params["agent"] = "coach_chat"
        params.pop("tension", None)
        return Intent(expert="chat", muscles=list(intent.muscles), raw=intent.raw, params=params)
    prior = _history_user_text(history)
    if not prior or not any(k in prior for k in _PLAN_THREAD_CUES):
        return intent
    params = dict(intent.params or {})
    params["agent"] = "coach_plan"
    muscles = list(intent.muscles)
    if not muscles:
        for cue, muscle in _THREAD_MUSCLES:
            if cue in prior or cue in raw:
                muscles = [muscle]
                break
    if not params.get("modality"):
        params["modality"] = ["抗阻"]
    return Intent(expert="training", muscles=muscles, raw=intent.raw, params=params)


def apply_coach_routing(
    intent: Intent,
    profile: Any | None = None,
    history: list[Any] | None = None,
) -> Intent:
    """按档案经验和长期目标决定是否反问。模型给出的 ready/tension 不参与。"""
    intent = _stick_to_open_plan(intent, history)
    if (intent.params.get("agent") or EXPERT_TO_AGENT.get(intent.expert)) != "coach_plan":
        return intent

    params = dict(intent.params or {})
    raw = intent.raw or ""

    from app.exercises_catalog import looks_like_exercise_name

    # 只清洗模型带来的点名，不再用热词表回填
    if params.get("focus_exercises"):
        cleaned = [n for n in params["focus_exercises"] if looks_like_exercise_name(n)]
        if cleaned:
            params["focus_exercises"] = cleaned
        else:
            params.pop("focus_exercises", None)

    # 已有明确强度 / 侧重 / 点名：清张力直接排。侧重可以在上一句（如「不够宽」之后的「111」）。
    prior_users = _history_user_text(history)
    if _ready_enough_to_plan(intent, params) or has_focus_detail(prior_users):
        if has_intensity_cue(raw):
            if any(k in raw for k in ("低强度", "恢复", "排酸", "慢走", "轻松有氧", "保肌肉")):
                params["intensity"] = "low"
            elif any(k in raw for k in ("高强度", "暴汗", "爆汗", "冲刺", "拉满", "练心肺", "大重量", "低次数", "力量为主")):
                params.setdefault("intensity", "high")
        params.pop("tension", None)
        params["ready"] = True
        return Intent(expert=intent.expert, muscles=list(intent.muscles), raw=intent.raw, params=params)

    exp = ""
    goal = params.get("goal") or ""
    if profile is not None:
        exp = profile.experience.value if hasattr(profile.experience, "value") else str(profile.experience)
        if not goal:
            goal = profile.goal.value if hasattr(profile.goal, "value") else str(profile.goal)

    raw = intent.raw or ""
    # 0) 出差场景：场地不明优先问场地
    if _is_blank_plan(intent) and any(k in raw for k in ("出差", "酒店", "旅馆", "民宿")):
        params["ready"] = False
        params["tension"] = {
            "has_tension": True,
            "kind": "safety",
            "question": "",
            "suggestions": [],
        }
        return Intent(expert=intent.expert, muscles=list(intent.muscles), raw=intent.raw, params=params)

    # 1) 完全空白：只标记要问「练什么」。话术交给模型，不按关键词写死。
    if _is_blank_plan(intent):
        params["ready"] = False
        params["tension"] = {
            "has_tension": True,
            "kind": "blank",
            "question": "",
            "suggestions": [],
        }
        return Intent(expert=intent.expert, muscles=list(intent.muscles), raw=intent.raw, params=params)

    # 2) 资深 + 大类目部位：只标记要问侧重，话术交给模型
    if exp == "老炮" and _broad_muscle_only(intent, params):
        muscle = next((m for m in intent.muscles if m != "全身"), "腿")
        params["ready"] = False
        params["tension"] = {
            "has_tension": True,
            "kind": "focus",
            "muscle": muscle,
            "question": "",
            "suggestions": [],
        }
        return Intent(expert=intent.expert, muscles=list(intent.muscles), raw=intent.raw, params=params)

    # 3) 增肌/力量 + 模糊有氧：只标记要问强度，不写死问句
    if goal in ("增肌", "力量") and _vague_cardio(intent):
        params["ready"] = False
        params["tension"] = {
            "has_tension": True,
            "kind": "intensity",
            "question": "",
            "suggestions": [],
        }
        return Intent(expert=intent.expert, muscles=list(intent.muscles), raw=intent.raw, params=params)

    # 新手/进阶大类目或已明确：开排
    if _plan_ready(list(intent.muscles), params):
        params["ready"] = True
        params.pop("tension", None)
    return Intent(expert=intent.expert, muscles=list(intent.muscles), raw=intent.raw, params=params)


def _focus_suggestions(muscle: str) -> list[dict[str, str]]:
    if muscle == "腿":
        return [
            {"label": "主攻股四前侧", "prompt": "今天练腿，主攻股四头肌前侧"},
            {"label": "主攻后链臀腿", "prompt": "今天练腿，主攻腘绳肌和臀后链"},
            {"label": "大复合深蹲", "prompt": "今天练腿，以杠铃深蹲为主力复合"},
        ]
    if muscle == "背":
        return [
            {"label": "宽度下拉", "prompt": "今天练背，主攻背阔宽度"},
            {"label": "厚度划船", "prompt": "今天练背，主攻中背厚度"},
            {"label": "硬拉力量", "prompt": "今天练背，以硬拉为主力"},
        ]
    if muscle == "胸":
        return [
            {"label": "上胸为主", "prompt": "今天练胸，主攻上胸"},
            {"label": "中缝泵感", "prompt": "今天练胸，主攻中缝泵感"},
            {"label": "卧推力量", "prompt": "今天练胸，以杠铃卧推为主力"},
        ]
    return [
        {"label": f"均衡练{muscle}", "prompt": f"今天均衡练{muscle}"},
        {"label": "复合打头", "prompt": f"今天练{muscle}，复合动作打头"},
        {"label": "细节雕刻", "prompt": f"今天练{muscle}，偏孤立细节"},
    ]


def needs_clarification(intent: Intent, has_draft: bool = False) -> bool:
    """出计划且存在张力/未就绪时反问。闲聊/营养不反问。"""
    agent = intent.params.get("agent") or EXPERT_TO_AGENT.get(intent.expert, "coach_chat")
    if agent != "coach_plan":
        return False
    if has_draft and is_draft_revision(intent.raw, intent.params):
        return False
    tension = intent.params.get("tension")
    if isinstance(tension, dict) and tension.get("has_tension"):
        # 点名动作 / 强度 / 侧重细节 → 不再拦
        if _ready_enough_to_plan(intent, intent.params):
            return False
        return True
    if intent.params.get("ready") is True:
        return False
    if _plan_ready(list(intent.muscles), intent.params):
        return False
    if user_named_target(intent.raw):
        return False
    return True


CLARIFY_SYSTEM = """【CLARIFY】
【角色】
你是 Gym Coach 的私人健身教练，正在和学员面对面沟通今日训练安排。

【任务】
当学员想训练但诉求还差关键一环时，用自然的一句话向学员追问确认，并提供 3~4 个可直接点击开练的快捷选项（suggestions）。

【背景】
输入可能包含：
1) 「近期对话」：今天到上一轮为止的聊天，用来顺着上文问。
2) 「更早会话」：用户在指以前的对话时才会出现。
3) 「学员属性」：系统后台的客观参数（训练经验档位、长期目标、伤痛等），仅供你决定追问深度与选项方向，绝不是学员的姓名、昵称或头衔。
4) 「要确认的点（kind）」：
   - blank：还没定练什么（注意「想出汗」不等于有氧，力量/HIIT/有氧都能出汗，需问清想练哪个部位或哪种课型）。
   - intensity：已定做有氧，但需结合长期目标确认今天是「低强度恢复/控心率」还是「高强度心肺/间歇」。
   - focus：已定大部位（如腿/胸/背），需确认今天的分化侧重（如股四/后链、力量/肌肥大）。
   - safety：存在伤痛或场地限制，需确认可接受的器械或动作范围。
   - session：已经有一堂计划，学员不满意这张，但没说部位留还是换。只问这一次。

【目标】
1) 顺着学员原话自然发问，像真人教练聊天，不背固定模板。
2) 给出的每个选项 prompt 必须是完整、明确的一句话，使得学员点选后下一轮无需再反问即可直接排课（一次问清，禁止连环追问）。

【约束】
1) 称呼准则：对学员一律称呼「你」或直接进入正题，严禁把任何「学员属性」里的词当成称呼、头衔或定语念出来。
2) 边界准则：只负责反问确认，不要在 text 里直接列出具体训练计划；不要篡改学员的长期目标，也不要禁止增肌期做有氧。
3) 选项准则：给 3~4 个差异化选项；label 简短（2~6 字）；focus 类 prompt 必须同时带上「部位侧重」；必要时可附带一种默认组次数风格（如大重量低次数或中等次数泵感），避免点选后还要再问强度/器械。
4) session 准则：学员没说不练当前部位，text 里就禁止出现「不练X了」。第一个选项必须是按当前部位再排一版动作。只问这一次。

【格式】
严格只输出以下 JSON：
{"text":"一句自然的中文反问","suggestions":[{"label":"短标签","prompt":"点击后发送的完整排课指令"}]}

【示例】
- 用户说：「今天随便出出汗」｜要确认的点：blank
  输出：{"text":"想出汗的话，今天更想拉一组全身循环、做有氧，还是挑个部位练力量？","suggestions":[{"label":"全身燃脂循环","prompt":"今天来个30分钟全身循环训练"},{"label":"痛快做有氧","prompt":"今天做高强度有氧出汗"},{"label":"练胸充血","prompt":"今天练胸肌抗阻训练"},{"label":"练腿暴汗","prompt":"今天练腿部力量训练"}]}
- 用户说：「做做有氧」｜长期目标：增肌｜要确认的点：intensity
  输出：{"text":"今天这趟有氧你想控制在低心率当主动恢复，还是拉高强度冲一下心肺？","suggestions":[{"label":"低心率恢复","prompt":"今天做30分钟低强度有氧恢复，不影响增肌恢复"},{"label":"中等稳态有氧","prompt":"今天做30分钟中等强度稳态有氧"},{"label":"高强度练心肺","prompt":"今天就想高强度有氧练心肺"}]}
- 用户说：「今天练腿」｜要确认的点：focus
  输出：{"text":"今天练腿想主打股四头肌、臀腿后链，还是整体都照顾到？","suggestions":[{"label":"主攻股四","prompt":"今天练腿，侧重股四头肌，中等次数泵感增肌"},{"label":"主攻后链","prompt":"今天练腿，侧重腘绳肌和臀部后链，大重量低次数"},{"label":"大小腿均衡","prompt":"今天练腿，前侧后链均衡安排，复合动作为主"}]}
- 用户说：「换个计划」｜当前计划部位：腿｜要确认的点：session
  输出：{"text":"这版腿计划你不想用了。是按腿再排一版动作，还是换成别的部位？","suggestions":[{"label":"腿再换一版","prompt":"部位不变，还是练腿，只换一套动作"},{"label":"换成练胸","prompt":"今天改练胸"},{"label":"换成练背","prompt":"今天改练背"},{"label":"全身练一轮","prompt":"今天改成全身力量"}]}

【自检】
输出前核对：
1) text 里是否完全没有把「学员属性」当称呼或标签念出来？
2) 每个 suggestion.prompt 单独发给排课器时，是否已经足够明确、不会再次触发反问？
"""


def _scrub_assumed_quit(text: str, user_text: str, open_target: str) -> str:
    """学员没否定当前部位时，去掉模型自作主张的「不练X了」。"""
    cleaned = text
    for muscle in [part for part in open_target.split("+") if part]:
        if f"不练{muscle}" in user_text or f"别练{muscle}" in user_text:
            continue
        for phrase in (f"那今天不练{muscle}了", f"今天不练{muscle}了", f"不练{muscle}了"):
            cleaned = cleaned.replace(phrase, f"这版{muscle}计划先放一边")
    return cleaned


def _scrub_level_address(text: str) -> str:
    """兜底：若模型仍把常见档位词当开头称呼，剥掉。"""
    cleaned = text.strip()
    for prefix in (
        "老炮儿，",
        "老炮儿,",
        "老炮，",
        "老炮,",
        "新手，",
        "进阶，",
        "多年训练，",
        "入门阶段，",
        "有训练基础，",
    ):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    return cleaned


async def generate_clarification(intent: Intent, profile_brief: str = "") -> tuple[str, list[dict[str, str]]]:
    """反问话术由模型写。失败才用一句中性兜底。"""
    client = get_intent_llm()
    tension = intent.params.get("tension") if isinstance(intent.params.get("tension"), dict) else {}
    kind = tension.get("kind") or "blank"
    open_target = str(intent.params.get("open_target") or tension.get("muscle") or "")
    user = (
        f"用户说：{intent.raw}\n"
        f"{profile_brief or '（无学员属性）'}\n"
        f"要确认的点：{kind}"
        + (f"\n当前计划部位：{open_target}" if kind == "session" and open_target else "")
        + (f"；部位={tension.get('muscle')}" if tension.get("muscle") and kind != "session" else "")
    )
    if client is not None:
        try:
            raw = await client.complete_json(CLARIFY_SYSTEM, user, temperature=TEMPERATURE_COPY)
            text = _scrub_level_address(str(raw.get("text") or ""))
            if kind == "session":
                text = _scrub_assumed_quit(text, intent.raw or "", open_target)
            options = _sanitize_tension({"has_tension": True, "question": text, "suggestions": raw.get("suggestions")})
            if text and options:
                return text, list(options["suggestions"])
        except Exception:  # noqa: BLE001
            pass
    if kind == "session" and open_target:
        part = open_target.split("+")[0]
        return (
            f"这版{part}计划你不想用了。是按{part}再排一版动作，还是换成别的部位？",
            [
                {"label": f"{part}再换一版", "prompt": f"部位不变，还是练{part}，只换一套动作"},
                {"label": "换成练胸", "prompt": "今天改练胸"},
                {"label": "换成练背", "prompt": "今天改练背"},
                {"label": "全身练一轮", "prompt": "今天改成全身力量"},
            ],
        )
    return (
        "今天想练什么？说一下部位或课型就行。",
        [
            {"label": "练胸", "prompt": "今天练胸"},
            {"label": "练背", "prompt": "今天练背"},
            {"label": "做有氧", "prompt": "今天做有氧"},
            {"label": "全身循环", "prompt": "全身循环30分钟"},
        ],
    )


def build_clarification(intent: Intent) -> tuple[str, list[dict[str, str]]]:
    """只有模型已经写好的反问才直接用。路由只标了要问时，把话术留空。"""
    tension = intent.params.get("tension")
    if isinstance(tension, dict) and tension.get("has_tension"):
        question = tension.get("question")
        suggestions = tension.get("suggestions")
        if isinstance(question, str) and question.strip() and isinstance(suggestions, list) and suggestions:
            return question, list(suggestions)
        return "", []

    raw = intent.raw
    if any(k in raw for k in ("出差", "酒店", "旅馆", "民宿")):
        return (
            "出差我还不确定你想怎么动。说一下，或点一个方向，我再排，不替你猜。",
            [
                {"label": "房间徒手", "prompt": "出差酒店房间，徒手练全身，20分钟"},
                {"label": "只有哑铃", "prompt": "酒店只有哑铃，练上半身"},
                {"label": "肩颈拉伸", "prompt": "出差久坐，肩颈拉伸放松，15分钟"},
            ],
        )
    if intent.params.get("fatigue"):
        return (
            "你说状态一般，但我还不知道想怎么动。说一下课型或部位，我按不加重来排。",
            [
                {"label": "轻松练背", "prompt": "今天没劲，轻松练背，别加重"},
                {"label": "只做核心", "prompt": "今天累，只做核心"},
                {"label": "轻松有氧", "prompt": "今天疲劳，轻松有氧20分钟"},
            ],
        )
    return (
        "可以排，但还不知道怎么练。说一下课型或部位，或点一个方向。",
        [
            {"label": "练胸", "prompt": "今天练胸"},
            {"label": "练背", "prompt": "今天练背"},
            {"label": "做有氧", "prompt": "今天做有氧"},
            {"label": "全身循环", "prompt": "全身循环30分钟"},
        ],
    )


def get_intent_llm() -> LLMClient | None:
    """意图改写专用模型槽。暂与主 LLM 相同；后续可独立配置更轻模型。"""
    provider = settings.intent_rewrite_provider
    if provider == "off":
        return None
    return get_llm()
