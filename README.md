# Gym Coach

个人训练 / 饮食记录 + AI 建议。方案见 `架构方案.md`；验收见 `阶段0-验收.md`、`阶段1-验收.md`。

## 本地启动

### 1. 后端（终端 A）

```bash
cd api
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 文档：http://127.0.0.1:8000/docs  
- 默认口令：`dev-token`（见 `api/.env` 的 `APP_TOKEN`）  
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
| `架构方案.md` | 定稿架构 |
| `设计系统.md` | UI token |
| `阶段0-验收.md` | 地基验收 |
| `阶段1-验收.md` | 训练闭环验收 |
| `项目演进与架构思考.md` | 阶段演进历程、工程细节与架构哲学沉淀 |

## 当前进度

**阶段 1**：四 Tab（今日 / 教练 / 训练 / 我的）、草稿可编辑与采纳、按组打卡、动作沉淀与上次重量回流。  
按 `阶段1-验收.md` 勾完即可。下一步可选阶段 2（饮食）或部署自用。
