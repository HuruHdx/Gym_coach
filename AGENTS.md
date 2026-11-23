# AGENTS.md

跨工具通用入口（Cursor / Codex / 其他 agent）。细则以代码与台账为准，本文只指路。

## 项目

个人训练计划工具。手机 H5（装主屏幕）+ FastAPI。  
核心闭环：对话/模板出今日计划 → 采纳 → 按组打卡 → 记录回流下次生成。

后台 UI 在独立仓 `gym-coach-admin`；本仓仍含 `/api/admin`。

## 唯一台账

**先读再改：** [`docs/项目地图.md`](docs/项目地图.md)

| 要了解 | 看地图 |
|---|---|
| 有什么能力 / 暂不做 | §1–§2 |
| 意图路由、模型工具、prompt 位置 | §3–§5 |
| 字段口径、配课原则 | §6 |
| 主要 HTTP / 卡片契约 | §7 |
| **改 A 会伤 B** | **§8 耦合表** |
| 评测、目录 | §9–§10 |
| 进行中大功能 | §11 |

H5 样式底线见 `.cursor/rules/gym-ui.mdc`；设计 token 在 `gym-ui/`（该目录另有 `AGENTS.md`）。

## 技术栈（极简）

- H5：`web/`（React + Vite）
- API：`api/`（FastAPI + SQLite 默认可跑）
- Agent：`api/app/brain/`
- 评测：仓库根 `eval/`（不写进地图正文）

## 改代码时

1. 动到相关模块 → 先读地图对应节 + **§8 耦合表**。  
2. 新增/变更能力、工具、表字段、prompt、HTTP/卡片契约 → **同一回合更新** `docs/项目地图.md`。  
3. 不确定产品意图 → 先问，不要猜。  
4. 不要新建平行「总览」md；长工单可留在 `docs/13-…` 等专题，但现状只维护地图一页。

## 常用命令

```bash
# API（在 api/ 下，视本机 venv）
# uvicorn / 项目既有启动方式

# H5
cd web && npm run dev
```
