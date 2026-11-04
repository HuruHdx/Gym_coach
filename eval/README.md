# eval/ · 问答评测（v0.5）

三份套件：

| 套件 | 文件 | 条数 | 作用 |
|---|---|---|---|
| **整体评测** | `cases.yaml` / `promptfooconfig.yaml` | 40 | 一句话进去，看整体回答对不对（内容 + 依据 + 行为） |
| **意图门禁** | `cases-intent.yaml` / `promptfooconfig-intent.yaml` | 35 | 改提示词时防 topic 回归 |
| **长对话** | `cases-long.yaml` / `promptfooconfig-long.yaml` | 22 | 一条对话链（1~4 轮）走下来，每步有没有走歪 |

设计说明：`../评测集-v0.4.md`、`../评测集-长对话.md`。

**三者的分工**：意图测「分类对不对」，整体测「答得好不好」，长对话测「流程会不会走着走着散掉」。
改提示词后的推荐顺序：意图（30 秒）→ 长对话（十几分钟，跑真实排课）→ 整体（最慢）。

## 整体评测的六组

| 组 | 条数 | 内容 |
|---|---|---|
| F 动作事实 | 12 | 练哪里 / 怎么做 / 区别 / 一类动作 / 俗称 |
| A 建议 | 7 | 练什么、练几次、要不要加、吃什么 |
| D 数据 | 5 | 我的数，含「没记录别编」 |
| S 安全 | 3 | 有伤能不能做 |
| B 边界 | 8 | 错字 / 英文 / 混合问句 / 长度 / 称呼 / 空输入 |
| R 非问答 | 5 | 排课、改稿、采纳、闲聊、饮食不占位 |

## 文件

| 文件 | 作用 |
|---|---|
| `cases.yaml` | 整体评测 40 条 |
| `cases-intent.yaml` | 意图门禁 35 条 |
| `cases-long.yaml` | 长对话 22 条（1~4 轮/条） |
| `promptfooconfig.yaml` / `-intent.yaml` / `-long.yaml` | 三个入口；各自挂 `defaultTest` 契约检查 |
| `provider.js` | **class**；调 `/api/eval/qa`，透传 `search_fixture` / `stats_fixture` |
| `provider-long.js` | **class**；调 `/api/eval/thread`，一次跑完整条对话，每轮结果进 metadata |
| `assertions/text.js` | 必含/禁含/字数/中文占比/禁 JSON/禁编重量 |
| `assertions/cites.js` | 引用了哪条、用词与被引条目 `target` 是否一致 |
| `assertions/stats.js` | 工具层（有没有查、过滤条件、命中哪条）+ 结果层（答案数字 == 工具返回值） |
| `assertions/branch.js` | route / branch / search.called / model_called / 选项 / sources |
| `assertions/shape.js` | 契约自洽（分支枚举、citations 只属 kb、suggestions 只属 ask） |
| `assertions/shape-long.js` | 长对话的契约自洽（每轮有 route、条目数与名单一致） |
| `assertions/topic.js` | 意图层：topic（plan/qa/chitchat） |
| `assertions/thread.js` | 长对话：按第 N 轮断言 route / 标题是否被改 / 条目数与名单 / 组数 / 伤痛 drop / 文案 |
| `assertions/adopt.js` | 长对话：采纳落库后的组数（含按卡片 `meta.sets` 核对）、动作名单、status |
| `assertions/selftest.js` / `selftest-topic.js` / `selftest-long.js` | 断言自测（45 + 12 + 43） |
| `probe_route.py` | 阶段 0 探针：不需要接口，内存库直接调图 |
| `out/` | 历史结果、A/B 证据、意图用例 CSV（跑过之后才会有） |

## 跑法

```bash
cd api && uv run uvicorn app.main:app --port 8000      # 终端 A

cd eval                                                # 终端 B
export PROMPTFOO_CONFIG_DIR="$PWD/.pf"                 # 必填，否则 SQLITE_READONLY
export DEEPSEEK_API_KEY=...
npx promptfoo eval --no-cache                          # 整体 40
npx promptfoo eval -c promptfooconfig-intent.yaml --no-cache   # 意图 35
npx promptfoo eval -c promptfooconfig-long.yaml --no-cache     # 长对话 22
npx promptfoo view
```

长对话跑的是**真实排课链路**（会真的出卡、真的采纳落库），一轮一次模型调用，比另外两套慢。
p0 用例已经带了 `metadata.p0=true`，想只跑核心链路：
`npx promptfoo eval -c promptfooconfig-long.yaml --filter-metadata p0=true`
（promptfoo 的 CLI 只按 metadata 过滤，`tags` 仅用于展示）。

Windows：`$env:PROMPTFOO_CONFIG_DIR = "$PWD\.pf"`。

## 怎么读红

| 标签 | 意思 | 处理 |
|---|---|---|
| `known_gap` | 代码还没改好（多肌群、混合问句） | 等 D-07，不是评测写错 |
| `blocked` | 接口缺字段（`stats_fixture`） | 端点补字段后再跑 |
| 无标签 | 真问题 | 看实际回答定 |

## 加用例的规矩

1. **先查库再写 id**（`name_zh` / `target` / 有没有中文步骤）。
2. **一条用例只锁它要测的那一层**：内容问题用 `text.js`，依据问题用 `cites.js`/`stats.js`，行为问题才用 `branch.js`。
3. **数字不写死**：要断言「用了工具返回值」，用 `stats.js` 的 `value_from_first_hit`。
4. **别为了让某条变绿去调阈值或改用例期望**。
5. **「不该出现某动作」别用 `text_has`/`text_not_has` 去碰文案**：卡片用 `items_not_has`，落库用 `exercises_none`。
6. **空断言等于没写**：`config` 里除了 `turn` 什么都不给，或者传 `exercises_has: []`，
   都是「恒过」。写完先跑自测，确认它在坏输入下会红。

改断言前后跑自测：`node eval/assertions/selftest.js`（45/45）、
`node eval/assertions/selftest-topic.js`（12/12）、`node eval/assertions/selftest-long.js`（43/43）。
