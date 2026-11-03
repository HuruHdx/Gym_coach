# AGENTS.md

跨工具通用的项目约定（Cursor / Codex / 其他 agent 都读这个）。

## 项目

个人训练计划工具。手机 H5，装到主屏幕。
核心闭环：生成今日计划 → 采纳或自己定制 → 按组勾选 → 改实际重量 → 写备注 → 下次生成读到这些记录。

## 技术栈

- 客户端：React + Vite，手机 H5
- 服务端：Python FastAPI
- 数据：服务器本机 SQLite（需要时改 Postgres）
- Agent：自写 harness + LangChain；饮食阶段用 LangGraph
- 观测：LangSmith

## 常用命令

```bash
npm run dev      # 本地开发
npm run build    # 构建
npx tsc --noEmit # 类型检查
```

## 样式约定（强制）

**所有 UI 改动必须遵守 `gym-ui/DESIGN.md`。**

- 颜色 / 圆角 / 字号 / 间距 / 动效 → 只用 `gym-ui/tokens.css` 的变量，禁止写死
- 组件类 → 复用 `gym-ui/components.css`，不要新造平行组件
- 主题切换 → `document.documentElement.dataset.theme`，不要在组件里判断主题

三条最容易犯、也最容易被 review 出来的：

1. 输入框字号必须是 16px（否则 iOS 聚焦会缩放整页）
2. 亮色品牌色只能当填充，当文字必须用 `--accent-text`（对比度 ≥ 4.5）
3. 只动画 `transform` / `opacity`

## 目录

```
gym-ui/           设计规范包（tokens / base / components / DESIGN / PROMPTS）
src/pages/        今日 · 训练 · 饮食 · 我的 · 教练
src/components/   复用组件
```

## 约束

- 不确定时提问，不要猜设计意图
- 不要为了"好看"引入新的字体、图标库或 UI 框架
- 不要改 `gym-ui/` 里的文件来迁就某个页面；要改就先说明理由
- 第一版只上线三个 Tab（今日 / 训练 / 我的），饮食是阶段 2
