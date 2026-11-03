# openGym 动作 / 中餐食物数据

## 文件

| 文件 | 说明 |
|------|------|
| `opengym_exercises_with_media.json` | 5632 条动作（含中英文名、部位、器械、步骤、图片路径） |
| `chinese_foods.sql` | 中国食物成分表（约 1677 种），**本阶段未接入教练链路** |
| 图片 | 已拷到 `api/static/exercises/`（约 95MB，gitignore），经 `/static/exercises/...` 可访问 |

来源： [openGym](https://github.com/DuarteSantos8/openGym) 文本 + [free-exercise-db](https://github.com/yuhonas/free-exercise-db) 图片（Public Domain）。食物来自中国食物成分表第 6 版整理数据。

## 导入 Postgres

在 `api/` 下：

```bash
uv run python scripts/import_opengym_exercises.py
```

运行时匹配 / 候选检索默认读本目录 JSON（无需先导入也能跑测试）；导入后写入 `exercise` 表供 SQL 与后续扩展。

## 许可注意

openGym 文本中部分条目属 AGPL 生态；图片为 Public Domain。商用前请自行评估。
