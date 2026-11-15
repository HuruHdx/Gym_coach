# Gym Coach

个人训练 / 饮食记录 + AI 建议。方案见 [`docs/architecture/架构方案.md`](./docs/architecture/架构方案.md)；历史验收见 [`docs/archive/`](./docs/archive/)。

## 后台 Admin（桌面另仓）

- 后台前端工程：`C:\Users\Huru Huru\Desktop\gym-admin`
- 后台方案与主进度以 `gym-admin/docs/`（01–05 路线图）为准，本仓不再保留副本

## 本地启动

### 1. 后端（终端 A）

```bash
cd api
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 文档：http://127.0.0.1:8000/docs  
- 前端登录：手机号 + 密码 → 返回 JWT；业务请求带 `Authorization: Bearer <token>`  
- 评测与脚本仍可用 `APP_TOKEN`（默认 `dev-token`，见 `api/.env`）  
- 生产请配置 `JWT_SECRET`  
- 默认模型：`LLM_PROVIDER=mock`（不需要 Key）

### 2. 前端（终端 B）

```bash
cd web
pnpm install
pnpm dev --host 127.0.0.1 --port 5173
```

浏览器打开：http://127.0.0.1:5173  

手机同网访问电脑 IP:5173（防火墙放行）。

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
| `api/` | FastAPI + SQLite + AI 内核骨架 |
| `web/` | React H5（Court/Cobalt/Ember 换肤） |
| `ui-preview/` | 静态 UI 画廊 |
| `docs/architecture/` | 定稿架构、设计系统、演进思考 |
| `docs/contracts/` | 意图路由契约、工单、知识问答方案 |
| `docs/eval/` | 评测架构与评测集说明 |
| `docs/archive/` | 已完成阶段的验收记录 |
| `docs/plan/` | 进行中的功能工单与方案 |

## 当前进度

**阶段 1**：四 Tab（今日 / 教练 / 训练 / 我的）、草稿可编辑与采纳、按组打卡、动作沉淀与上次重量回流。  
按 [`docs/archive/阶段1-验收.md`](./docs/archive/阶段1-验收.md) 勾完即可。下一步可选阶段 2（饮食）或部署自用。
