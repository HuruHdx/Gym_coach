"""阶段 0 探针：只跑「意图 → 回答」这条现存链路，用来给评测集做首轮校准。

为什么单独写：
- POST /api/chat 会写 ChatTurn / Profile / DebugTrace，跑一轮评测就污染真实库；
- POST /api/eval/qa 还没实现，promptfoo 还接不上。
所以这里用内存 SQLite + 直接调图，不落库、不碰 Postgres。

它测的是「今天已经能测的东西」：route / 意图槽位 / 回答文本。
它不测：kb 分支、检索分数、search.called —— 那些要等 ground_knowledge 落地。

用法：
    cd api && uv run python eval/probe_route.py            # 全部
    cd api && uv run python eval/probe_route.py --only K01,M01
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 默认本文件在 <项目根>/eval/ 下，也可以放在 <api>/eval/；
# GYM_COACH_API 可显式指向 api 目录。
_HERE = Path(__file__).resolve().parent
API_DIR = Path(os.environ.get("GYM_COACH_API") or "")
if not str(API_DIR):
    for _cand in (_HERE.parent, _HERE.parent / "api"):
        if (_cand / "app").is_dir():
            API_DIR = _cand
            break
    else:
        API_DIR = _HERE.parent
sys.path.insert(0, str(API_DIR))


def _load_env() -> None:
    """pydantic-settings 的 env_file 相对 cwd，这里手动装一遍，避免 cwd 不同读不到 key。"""
    env_file = API_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()

from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app.brain.graph import invoke_chat_graph  # noqa: E402
from app.models import Experience, Goal, Profile  # noqa: E402

# 评测夹具：新手、无伤痛、无历史（需求文档 §5.1）
FIXTURE_NOVICE = dict(goal=Goal.BULK, experience=Experience.NOVICE, weight_kg=70.0, days_per_week=4)
FIXTURE_ADVANCED = dict(goal=Goal.BULK, experience=Experience.ADVANCED, weight_kg=72.0, days_per_week=4)
FIXTURE_LOWBACK = dict(
    goal=Goal.BULK, experience=Experience.NOVICE, weight_kg=70.0, days_per_week=4, injuries=["腰"]
)

DRAFT_AEROBIC = dict(
    draft_title="有氧",
    draft_items=[
        {"id": "c1", "title": "跑步", "selected": True, "meta": {"sets": 1, "reps": "20分钟", "muscle": "全身"}},
        {"id": "c2", "title": "坐姿划船", "selected": True, "meta": {"sets": 1, "reps": "15分钟", "muscle": "背"}},
        {"id": "c3", "title": "动感单车", "selected": True, "meta": {"sets": 1, "reps": "10分钟", "muscle": "全身"}},
    ],
)

CASES: list[dict] = [
    # 知识问答（走 chat_reply，今天就能跑）
    {"id": "K01", "profile": FIXTURE_NOVICE, "q": "杠杆坐姿划船练哪里", "expect_route": "chat"},
    {"id": "K02", "profile": FIXTURE_NOVICE, "q": "杠杆坐姿划船怎么做", "expect_route": "chat"},
    {"id": "K03", "profile": FIXTURE_NOVICE, "q": "深蹲练哪里", "expect_route": "chat"},
    {"id": "K04", "profile": FIXTURE_NOVICE, "q": "硬拉练哪里", "expect_route": "chat"},
    {"id": "K05", "profile": FIXTURE_NOVICE, "q": "山羊挺身练哪里", "expect_route": "chat"},
    {"id": "K07", "profile": FIXTURE_NOVICE, "q": "弹力带交替二头弯举怎么做", "expect_route": "chat"},
    {"id": "S03", "profile": FIXTURE_NOVICE, "q": "悍马划船练哪里", "expect_route": "chat"},
    {"id": "S04", "profile": FIXTURE_NOVICE, "q": "股四头肌练哪里", "expect_route": "chat"},
    {"id": "A01", "profile": FIXTURE_NOVICE, "q": "高位下拉练哪里", "expect_route": "chat"},
    {"id": "A02", "profile": FIXTURE_NOVICE, "q": "坐姿划船练哪里", "expect_route": "chat"},
    {"id": "A03", "profile": FIXTURE_NOVICE, "q": "卧推练哪里", "expect_route": "chat"},
    {"id": "C01", "profile": FIXTURE_NOVICE, "q": "哑铃单臂俯身划船练哪里", "expect_route": "chat"},
    {"id": "S01", "profile": FIXTURE_NOVICE, "q": "新手一周练几次背合适", "expect_route": "chat"},
    {"id": "S06", "profile": FIXTURE_NOVICE, "q": "一周练几次腿", "expect_route": "chat"},
    # 个人记录
    {"id": "M01", "profile": FIXTURE_NOVICE, "q": "我上次卧推多少", "expect_route": "chat"},
    {"id": "M04", "profile": FIXTURE_NOVICE, "q": "我体重多少", "expect_route": "chat"},
    {"id": "M03", "profile": FIXTURE_LOWBACK, "q": "我腰不好，硬拉能做吗", "expect_route": "chat"},
    # 回答约束
    {"id": "G02", "profile": FIXTURE_ADVANCED, "q": "深蹲怎么练", "expect_route": "chat"},
    {"id": "G04", "profile": FIXTURE_LOWBACK, "q": "硬拉怎么做", "expect_route": "chat"},
    # 路由
    {"id": "R01", "profile": FIXTURE_NOVICE, "q": "今天练背", "expect_route": "plan", "skip_llm": True},
    {"id": "R02", "profile": FIXTURE_ADVANCED, "q": "今天练背", "expect_route": "clarify"},
    {"id": "R03", "profile": FIXTURE_NOVICE, "q": "今天练", "expect_route": "clarify"},
    {"id": "R05", "profile": FIXTURE_NOVICE, "q": "就这个吧，今天的计划", "expect_route": "chat", **DRAFT_AEROBIC},
    {"id": "R06", "profile": FIXTURE_NOVICE, "q": "今天吃什么蛋白粉", "expect_route": "nutrition"},
    {"id": "R08", "profile": FIXTURE_NOVICE, "q": "那高位下拉和划船有啥区别", "expect_route": "chat",
     "history": [
         {"role": "user", "text": "今天练背"},
         {"role": "assistant", "text": "安排好了", "card_title": "背训", "card_items": ["高位下拉", "坐姿划船"]},
     ]},
]


def _session(profile_kwargs: dict, with_history: list | None = None) -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(Profile(**profile_kwargs))
    session.commit()
    return session


async def run_case(case: dict) -> dict:
    started = time.perf_counter()
    session = _session(case["profile"])
    try:
        state = await invoke_chat_graph(
            session,
            user_text=case["q"],
            draft_title=case.get("draft_title"),
            draft_items=case.get("draft_items") or [],
            history=case.get("history") or [],
        )
    finally:
        session.close()
    blocks = state.get("blocks") or []
    answer = "\n".join(b.get("text") or "" for b in blocks if b.get("kind") == "text")
    cards = [b for b in blocks if b.get("kind") == "card"]
    intent = state.get("intent") or {}
    params = intent.get("params") or {}
    return {
        "id": case["id"],
        "question": case["q"],
        "expect_route": case.get("expect_route"),
        "route": state.get("route"),
        "route_ok": state.get("route") == case.get("expect_route"),
        "agent": params.get("agent"),
        "muscles": intent.get("muscles"),
        "focus_exercises": params.get("focus_exercises"),
        "rewrite": params.get("rewrite"),
        "answer": answer,
        "answer_len": len(answer),
        "has_card": bool(cards),
        "nodes": [s.get("node") for s in (state.get("steps") or [])],
        "ms": int((time.perf_counter() - started) * 1000),
    }


async def main(only: set[str] | None) -> None:
    out_dir = Path(__file__).resolve().parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = out_dir / f"probe-{stamp}.jsonl"

    rows = []
    for case in CASES:
        if only and case["id"] not in only:
            continue
        if case.get("skip_llm"):
            # 排课会走工具循环，成本高；路由已由 R02/R03/R08 覆盖
            print(f"[skip] {case['id']} {case['q']}（排课链路，见文档说明）")
            continue
        try:
            row = await run_case(case)
        except Exception as exc:  # noqa: BLE001
            row = {"id": case["id"], "question": case["q"], "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        with out_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        mark = "ok " if row.get("route_ok") else "FAIL"
        print(f"[{mark}] {row['id']} route={row.get('route')} exp={row.get('expect_route')} "
              f"agent={row.get('agent')} answer={str(row.get('answer'))[:70]!r}")

    total = len(rows)
    passed = sum(1 for r in rows if r.get("route_ok"))
    print(f"\n路由：{passed}/{total} 通过；明细 {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    asyncio.run(main(only))
