# Gym Coach

个人训练助手（对话出计划 → 采纳打卡 → 记录回流）+ 计划模板。  
**项目现状只看一页**：[`docs/项目地图.md`](./docs/项目地图.md)（建议用 Obsidian 打开）。

## 后台 Admin（另仓）

- 工程：`gym-coach-admin`
- 方案以 admin 仓 `docs/` 为准

## 本地启动

### 1. 后端（终端 A）

```bash
cd api
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 文档：http://127.0.0.1:8000/docs  
- 前端登录：手机号 + 密码 → JWT；业务请求带 `Authorization: Bearer <token>`  
- 评测与脚本仍可用 `APP_TOKEN`（默认 `dev-token`，见 `api/.env`）  
- 生产请配置 `JWT_SECRET`  
- 默认模型：`LLM_PROVIDER=mock`

### 2. 前端（终端 B）

```bash
cd web
pnpm install
pnpm dev --host 127.0.0.1 --port 5173
```

浏览器：http://127.0.0.1:5173  

### 3. 切真模型（可选）

编辑 `api/.env`：

```
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

## 目录

| 路径 | 说明 |
|------|------|
| `api/` | FastAPI + AI 内核 |
| `web/` | React H5 |
| `eval/` | 评测用例与断言 |
| `docs/项目地图.md` | **唯一**项目台账 |
| `gym-ui/` | 设计 tokens / DESIGN |

## 当前进度

训练主线已可用（计划 / 打卡 / 动作库 / 计划模板）。营养阶段未开工。细节以项目地图为准。
