# 意图 topic 改造工单 v2（交给项目 AI 执行）

> 目标：`/api/eval/qa` 返回 `intent.topic`（3 值）+ `intent.domain`（3 值）+ `stats`，路由按 topic 走。
> 验收：`eval/cases-intent.yaml` **35/35**（只锁 `topic`）；`pytest` 不回归。
> 契约：`意图分类与路由契约.md`（v2）。**本工单只做意图这一刀**，不改知识层的内容质量。

---

## 0. 一句话

`coach_chat` 里塞着知识、数据、闲聊。这一刀把它拆成 `qa` / `chitchat` 两个 topic，
「问自己的数据」**不是 topic**，改成把统计注入上下文（数据是上下文，不是分类）。
`nutrition` 降级为 `domain`，不再是一级分类。

---

## 1. 改动清单

| # | 文件 | 改什么 |
|---|---|---|
| 1 | `api/app/brain/intent_rewrite.py` | 提示词加 `topic` / `domain`；解析并写入 `params`；`agent` 兼容映射 |
| 2 | `api/app/brain/graph.py` | `_pick_route` 按 topic 映射（无 topic 退回旧逻辑） |
| 3 | `api/app/brain/knowledge_reply.py` | **复用 `get_related_stats` + 精确名查询**，把【训练统计】注入提示词 |
| 4 | `api/app/routers/brain.py` | `/api/eval/qa` 返回 `intent.topic`、`intent.domain`、`stats` |
| 5 | `api/tests/test_intent_rewrite.py` | topic/domain 解析 + 路由映射单测 |
| 6 | （建议）`/api/eval/qa` | 加 `mode=intent`：只跑意图、跳过回答生成 |

> `domain` 可以在这一步一并输出并落 `params`，但**不参与验收**；路由与细分另有后续层。

**不要动**：`branch` 枚举、`retrieve_knowledge`、`_ask()`、排课工具循环、`assemble_memory`。

---

## 2. 提示词（`INTENT_REWRITE_SYSTEM`）

在【分流 agent】之前插入：

```text
【topic 主分类】
先判这句话要交付什么，再填 agent。

topic 只能是三个：
- plan      要一份安排：排课、改稿、换动作、选今天练什么、排饮食计划。
- qa 要解释、建议、对比、做法，或要他自己的数据（上次多少、体重、这个月几次）。
- chitchat  寒暄、情绪、闲话，既不要安排也不要知识。

domain 只能是三个，只表示领域，不影响 topic：
- training   动作、训练方法、训练数据
- nutrition  饮食、热量、补剂
- general    其它

判定顺序：plan → qa → chitchat。

判据：
- plan 的判据是「要不要产出一份安排」。句子里提了历史、部位、动作都不影响。
- qa 的判据是「要不要解释/建议/数据」。
- chitchat 是兜底：有「练」字但没要安排，也不是问知识。

示例（必须照这个判）：
- 今天练胸，卧推按上次的重量来 → plan（历史是约束，不是主题）
- 明天练胸还是练背好 → plan（在选安排，不是比动作）
- 帮我排个减脂餐 → plan + nutrition
- 我腰不好，硬拉能做吗 → qa（不是 plan）
- 昨天练背，今天背有点疼正常吗 → qa（不是 plan）
- 练完要不要马上补碳水 → qa + nutrition
- 蛋白粉和增肌粉哪个好 → qa + nutrition
- 我上次卧推多少 → qa（要数据，数据由工具给）
- 今天心情不好，不想练 → chitchat（不是 plan）
```

【格式】骨架里加两行：

```json
"topic": "plan|qa|chitchat",
"domain": "training|nutrition|general",
```

---

## 3. 解析（`intent_from_model_json`）

```python
ALLOWED_TOPICS = {"plan", "qa", "chitchat"}
ALLOWED_DOMAINS = {"training", "nutrition", "general"}
TOPIC_TO_AGENT = {"plan": "coach_plan", "qa": "coach_chat", "chitchat": "coach_chat"}

topic = raw.get("topic")
if isinstance(topic, str) and topic in ALLOWED_TOPICS:
    params["topic"] = topic
    agent = TOPIC_TO_AGENT[topic]        # topic 为准，agent 跟着变

domain = raw.get("domain")
if isinstance(domain, str) and domain in ALLOWED_DOMAINS:
    params["domain"] = domain
```

规则：

- 非法/缺失 → **不写** `params`，不要兜底猜（评测要能看见"模型没按格式输出"）；
- `params["agent"]` 仍然写，下游在读。

---

## 4. 路由（`graph._pick_route`）

```python
def _pick_route(intent, has_draft):
    params = intent.params or {}
    topic = params.get("topic")
    domain = params.get("domain")

    if params.get("adopt_hint"):
        return "chat"                       # 口头采纳，不走排课

    if topic == "plan":
        if domain == "nutrition":
            return "nutrition"              # 饮食计划：仍走占位
        if has_draft and is_draft_revision_safe(intent):
            return "plan"
        return "clarify" if needs_clarification(intent, has_draft=has_draft) else "plan"

    if topic in ("qa", "chitchat"):
        return "chat"

    # 没有 topic：退回旧逻辑
    ...（保留现有实现）
```

---

## 5. 知识分支注入统计（`knowledge_reply.py`）

现在只注入了画像（`build_profile_summary`），**没取统计**。改成：

```python
from sqlmodel import select
from app.brain.tools import build_tool_context, execute_tool
from app.models import ExerciseStats
from app.taxonomy import canonicalize_exercise

ctx = build_tool_context(session, intent, profile)

# ① 原句点名的动作：精确取那一条
names = list(intent.params.get("focus_exercises") or []) + _contained_names(question)
rows = []
for name in names[:2]:
    row = session.exec(
        select(ExerciseStats).where(ExerciseStats.exercise_name == canonicalize_exercise(name))
    ).first()
    if row:
        rows.append(row)

# ② 不够再按部位取（复用排课那套过滤，不要另写）
tool_calls = []
if len(rows) < 3:
    got = execute_tool("get_related_stats", {"muscles": intent.muscles, "limit": 4}, ctx)
    tool_calls = ctx.tool_trace[-1:]
    stats_text = got.get("text") or ""
else:
    stats_text = "\n".join(_format_stat_line(r) for r in rows)

long_term = f"【长期记忆】\n{profile_text}\n【训练统计】\n{stats_text or '（暂无）'}"
```

要点：

- **不要**把全部 26 条统计倒进去；「练什么拿什么」用 `intent.muscles`，点名动作优先；
- 过滤复用 `get_related_stats`（它已按 `roles_of` + `modalities` 过滤），不要复制一份逻辑；
- `stats_text` 为空时写「（暂无）」，让模型能说「没有记录」。

---

## 6. 响应字段（`/api/eval/qa`）

```python
"intent": {"agent": ..., "topic": params.get("topic"), "domain": params.get("domain"), ...},
"stats": {
    "queried": bool(rows) or bool(tool_calls),
    "filter": {"muscles": intent.muscles, "names": names[:2]},
    "tool_calls": [{"tool": "get_related_stats", "args": {"muscles": intent.muscles, "limit": 4}}],
    "hits": [
        {"name": r.exercise_name, "last_weight": r.last_weight, "last_reps": r.last_reps, "trend": r.trend}
        for r in rows
    ],
},
```

`hits` 必须是**结构化**的（不是拼好的句子），否则评测没法做「答案里的数字 == 工具返回值」这种动态比对。

---

## 7. 单测

1. `topic="qa"` → `params["topic"]=="qa"` 且 `agent=="coach_chat"`；
2. `topic="plan"` → `agent=="coach_plan"`；
3. `topic="chitchat"` → `agent=="coach_chat"`；
4. `topic="memory"`（旧值/非法）→ `params` 无 topic，不抛异常；
5. `domain="nutrition"` → `params["domain"]=="nutrition"`；非法同理；
6. `_pick_route`：`plan+training→plan`、`plan+nutrition→nutrition`、`qa→chat`、`chitchat→chat`。

---

## 8. 验收

```bash
cd api && uv run pytest -q
cd api && uv run uvicorn app.main:app --port 8000
cd eval && npx promptfoo eval -c promptfooconfig-intent.yaml --no-cache
```

- 意图：**35/35**（只锁 topic；domain/route 不在本层验收）；
- 红的原因只有两种：`topic=xxx want=yyy`（提示词判据）或 `intent.topic 未返回`（代码没接上）。

---

## 9. 不要做

- ❌ 不要保留 `nutrition` 作为 topic（它是 domain）；只有 `plan+nutrition` 才走 nutrition 路由。
- ❌ 不要新增 `lookup` / `memory` topic；数据走上下文。
- ❌ 不要把 topic 写进 `branch`，`branch` 枚举不变。
- ❌ 不要删 `_KNOWLEDGE_CUES` / `_stick_to_open_plan`（等这一刀稳定、主集不回归再删）。
- ❌ 不要为了让评测变绿去改用例期望（8 条 boundary 是故意写的）。

---

## 10. 这一刀之后

| 套件 | 现在 | 之后 |
|---|---|---|
| 意图 30 条 | 全红 | 30/30 |
| 主集 52 条 | 38/52 | 不变（这一刀不改知识层内容） |
| 数据正确性 5 条 | 未加入 | 等 `stats` 字段落地后加入 |

---

## 11. 迭代手册（改完代码之后怎么用这套评测）

### 11.1 第一次：把字段接上

```bash
cd api && uv run pytest -q                 # 单测不回归
cd api && uv run uvicorn app.main:app --port 8000
cd eval && npx promptfoo eval -c promptfooconfig-intent.yaml --no-cache
```

- 若 35 条全是 `intent.topic 未返回` → 字段没接上，回到 §3 / §6。
- 若有 `topic=xxx want=yyy` → 进入 11.2。

### 11.2 循环：只改一条判据

1. 看红的那条的 `reason`：`topic=plan want=qa` = 模型判成排课了。
2. **一次只改一处**：要么补一条示例，要么改一句判据，不要两样一起改。
3. 重跑（30 秒内出结果），对比「红的条数」和「红的 id」。
4. 只关心两件事：**红的变少了吗？原来绿的变红了吗？**（后者叫回归，比前者更重要）
5. 连续两轮没有变好，说明这条判据本身有歧义——把那条用例标 `decision_pending`，先跳过。

### 11.3 允许的改动顺序（从便宜到贵）

| 顺序 | 改什么 | 什么时候 |
|---|---|---|
| 1 | 补/改提示词里的**示例** | 只有个别 id 红 |
| 2 | 改**判据措辞**（plan/knowledge 的定义句） | 一类句子成片红 |
| 3 | 调整**判定顺序**（plan → qa → chitchat） | 发现同一句两边都像 |
| 4 | 动用例本身 | **最后**，且要先确认是期望写错了 |

### 11.4 什么时候算稳定

- 连跑 3 次都是 35/35（排除抖动）；
- 换一次夹具（比如把 `profile` 换成老炮）跑，仍然 35/35——topic 不该受画像影响；
- 这时再把 `_KNOWLEDGE_CUES` / `_stick_to_open_plan` 删掉，删完再跑一次确认。

### 11.5 常见红的解读

| reason | 意思 | 先查 |
|---|---|---|
| `intent.topic 未返回` | 代码没接上 | §3 解析 / §6 响应 |
| `topic=plan want=qa` | 把问答判成排课 | 判据「要不要产物」+ 补示例 |
| `topic=qa want=plan` | 把排课判成问答 | 「今天练背」这类要出卡的句子 |
| `topic=chitchat want=qa` | 把知识问句当闲聊 | 「练胸还是练背」这种给建议的 |
| `topic=qa want=chitchat` | 把闲聊当问答 | 只有情绪、没有训练对象的句子 |
| `topic=memory 不在枚举内` | 模型还在输出旧值 | 提示词枚举没更新 |
