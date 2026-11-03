# eval/inbox · 差评回流草稿

线上聊天点踩后，用脚本导出到这里：

```bash
cd api && uv run python scripts/export_feedback_inbox.py
```

- 文件形如 `FB-<id>-<slug>.yaml`，带 `vars` + `meta.observed` + 占位 `assert`
- **未审不进 CI / 不进正式绿集**；审过后才拷进 `cases.yaml` / `cases-target.yaml` 并补全断言
- 本目录下的 `FB-*.yaml` 已 gitignore，只保留本 README
