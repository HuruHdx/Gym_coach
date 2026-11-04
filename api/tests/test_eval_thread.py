"""长对话评测接口 /api/eval/thread 的单测。

重点不是「模型答得好不好」，而是**草稿有没有在轮次之间正确传递** ——
这是整条链路唯一由服务端保管的状态，错了就测不出真实行为。

另外两条回归守着长对话评测的前提：接口默认要**真的出卡**（曾经传 eval_mode=True，
plan 被短路成 eval_shortcut，卡片永远为空，cases-long.yaml 里的断言全部无解）。

  cd api && uv run pytest tests/test_eval_thread.py -q
"""

from __future__ import annotations

import asyncio

from app.routers.brain import _thread_turn, _to_draft_items, _turn_cards


def _card(title: str, items: list[dict]) -> dict:
    return {
        "kind": "card",
        "card_type": "training_draft",
        "title": title,
        "items": items,
        "meta": {"dropped": []},
    }


def _state(route: str = "plan", blocks: list[dict] | None = None, **params) -> dict:
    return {
        "route": route,
        "blocks": blocks or [],
        "intent": {"params": dict(params)},
        "suggestions": [],
    }


# ---------- 卡片提取 ----------


def test_turn_cards_picks_first_card():
    state = _state(
        blocks=[
            {"kind": "text", "text": "排好了"},
            _card("胸训", [{"title": "哑铃卧推", "selected": True, "meta": {"sets": 4}}]),
        ]
    )
    title, items = _turn_cards(state)
    assert title == "胸训"
    assert len(items) == 1


def test_turn_cards_returns_none_when_no_card():
    title, items = _turn_cards(_state(route="chat", blocks=[{"kind": "text", "text": "讲讲"}]))
    assert title is None
    assert items == []


# ---------- 卡片 → 下一轮 draft_items ----------


def test_draft_items_only_keeps_selected():
    items = [
        {"title": "哑铃卧推", "selected": True, "meta": {"sets": 4, "reps": "8-10"}},
        {"title": "龙门架夹胸", "selected": False, "meta": {"sets": 3}},
        {"title": "上斜哑铃推", "selected": True, "meta": {"sets": 3}},
    ]
    draft = _to_draft_items(items)
    assert [d.title for d in draft] == ["哑铃卧推", "上斜哑铃推"]
    assert all(d.selected for d in draft)
    # meta 必须原样带下去，否则下一轮拿不到组次/重量
    assert draft[0].meta == {"sets": 4, "reps": "8-10"}


def test_draft_items_defaults_to_selected_when_flag_missing():
    """旧卡片可能没有 selected 字段，按选中处理。"""
    draft = _to_draft_items([{"title": "杠铃卧推", "meta": {}}])
    assert len(draft) == 1


def test_draft_items_empty_when_all_unselected():
    draft = _to_draft_items([{"title": "x", "selected": False, "meta": {}}])
    assert draft == []


# ---------- 单轮结果 ----------


def test_thread_turn_counts_and_dropped():
    state = _state(
        blocks=[
            {"kind": "text", "text": "按你的情况排好了"},
            {
                "kind": "card",
                "title": "腿训",
                "items": [
                    {"title": "腿举", "selected": True, "meta": {}},
                    {"title": "保加利亚分腿蹲", "selected": False, "meta": {}},
                ],
                "meta": {"dropped": ["杠铃硬拉"]},
            },
        ],
        topic="plan",
        draft_relation="revise",
    )
    turn = _thread_turn(1, "今天练腿", state)
    assert turn.index == 1
    assert turn.route == "plan"
    assert turn.topic == "plan"
    assert turn.draft_relation == "revise"
    assert turn.card_title == "腿训"
    assert turn.card_item_count == 2
    assert turn.selected_count == 1
    assert turn.dropped == ["杠铃硬拉"]
    assert turn.text_block == "按你的情况排好了"


def test_thread_turn_without_card():
    turn = _thread_turn(0, "深蹲练哪里", _state(route="chat", blocks=[{"kind": "text", "text": "练腿"}], topic="qa"))
    assert turn.card_title is None
    assert turn.card_item_count == 0
    assert turn.route == "chat"


# ---------- 跨轮传递（用假图模拟，不依赖模型） ----------


def _run_fake_thread(script: list[dict]) -> list[str | None]:
    """
    模拟 eval_thread 的轮间逻辑：每轮拿到 title 就替换草稿，没拿到就沿用。
    返回每轮结束时「下一轮会带上」的草稿标题。
    """
    draft_title: str | None = None
    draft_items = []
    carried: list[str | None] = []
    for i, state in enumerate(script):
        title, items = _turn_cards(state)
        if title:  # 出了新卡 → 覆盖
            draft_title = title
            draft_items = _to_draft_items(items)
        carried.append(draft_title)
        _ = i
    return carried


def test_draft_survives_qa_turn():
    """排课 → 问知识（不出卡）→ 草稿不能被冲掉。"""
    script = [
        _state(blocks=[_card("胸训", [{"title": "哑铃卧推", "selected": True, "meta": {}}])]),
        _state(route="chat", blocks=[{"kind": "text", "text": "手腕这样放…"}], topic="qa"),
        _state(blocks=[_card("胸训", [{"title": "上斜哑铃推", "selected": True, "meta": {}}])]),
    ]
    carried = _run_fake_thread(script)
    assert carried == ["胸训", "胸训", "胸训"]


def test_draft_replaced_on_new_plan():
    """换部位 → 标题必须变。"""
    script = [
        _state(blocks=[_card("腿训", [{"title": "腿举", "selected": True, "meta": {}}])]),
        _state(blocks=[_card("背训", [{"title": "高位下拉", "selected": True, "meta": {}}])]),
    ]
    carried = _run_fake_thread(script)
    assert carried == ["腿训", "背训"]


# ---------- 请求体校验 ----------


def test_request_defaults():
    from app.schemas import EvalThreadRequest, EvalTurnIn

    body = EvalThreadRequest(turns=[EvalTurnIn(text="今天练胸")])
    assert body.search_mode == "fixture"
    assert body.adopt_after is None
    assert body.profile is None
    # 长对话默认走真实排课链路（要出卡），短路必须显式打开
    assert body.short_circuit is False
    assert len(body.turns) == 1


def test_request_rejects_empty_turns():
    import pytest
    from pydantic import ValidationError

    from app.schemas import EvalThreadRequest

    with pytest.raises(ValidationError):
        EvalThreadRequest(turns=[])


def test_request_rejects_too_many_turns():
    import pytest
    from pydantic import ValidationError

    from app.schemas import EvalThreadRequest, EvalTurnIn

    with pytest.raises(ValidationError):
        EvalThreadRequest(turns=[EvalTurnIn(text=f"第{i}句") for i in range(13)])


# ---------- 接口冒烟（不调模型：mock 掉 invoke_chat_graph） ----------


def test_eval_thread_endpoint_smoke(monkeypatch):
    """走一遍真实路由，确认草稿在轮间被正确传递。"""
    import app.brain.graph as graph_mod
    from fastapi.testclient import TestClient

    from app.auth import require_token
    from app.main import app

    seen: list[dict] = []

    async def fake_invoke(session, *, user_text, draft_title, draft_items, **kwargs):
        seen.append(
            {
                "user_text": user_text,
                "draft_title": draft_title,
                "draft_items": [d.title for d in draft_items],
            }
        )
        # 第 1 轮出卡；第 2 轮不出卡（模拟问知识）
        if len(seen) == 1:
            return _state(
                blocks=[
                    {"kind": "text", "text": "排好了"},
                    _card(
                        "胸训",
                        [
                            {"title": "哑铃卧推", "selected": True, "meta": {"sets": 4}},
                            {"title": "龙门架夹胸", "selected": False, "meta": {"sets": 3}},
                        ],
                    ),
                ],
                topic="plan",
            )
        return _state(route="chat", blocks=[{"kind": "text", "text": "手腕别塌"}], topic="qa")

    monkeypatch.setattr(graph_mod, "invoke_chat_graph", fake_invoke)
    app.dependency_overrides[require_token] = lambda: "test-token"

    client = TestClient(app)
    res = client.post(
        "/api/eval/thread",
        headers={"Authorization": "Bearer test-token"},
        json={
            "name": "smoke",
            "turns": [{"text": "今天练胸"}, {"text": "哑铃卧推手腕怎么放"}],
            "profile": {"goal": "增肌", "experience": "进阶", "weight_kg": 70, "days_per_week": 4},
        },
    )
    app.dependency_overrides.clear()

    assert res.status_code == 200, res.text
    data = res.json()
    assert len(data["turns"]) == 2
    assert data["turns"][0]["card_title"] == "胸训"
    assert data["turns"][0]["selected_count"] == 1
    assert data["turns"][1]["card_title"] is None

    # 第 2 轮应该带着第 1 轮的草稿和选中项
    assert seen[1]["draft_title"] == "胸训"
    assert seen[1]["draft_items"] == ["哑铃卧推"]


def test_eval_thread_reports_round_failure(monkeypatch):
    """某一轮抛异常时，要带上是第几轮，而不是整体 500。"""
    import app.brain.graph as graph_mod
    from fastapi.testclient import TestClient

    from app.auth import require_token
    from app.main import app

    async def boom(*args, **kwargs):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(graph_mod, "invoke_chat_graph", boom)
    app.dependency_overrides[require_token] = lambda: "t"

    client = TestClient(app)
    res = client.post(
        "/api/eval/thread",
        headers={"Authorization": "Bearer t"},
        json={"turns": [{"text": "今天练胸"}]},
    )
    app.dependency_overrides.clear()

    assert res.status_code == 200
    assert "第 1 轮失败" in (res.json().get("error") or "")


# ---------- 回归：默认必须走真实排课链路（出卡 → 改稿 → 采纳） ----------


def _patch_plan(monkeypatch, items):
    """把意图改写与排课模型都换成假的，被测的只剩图与接口本身。"""
    import app.brain.graph as graph_mod
    from app.brain.memory import Intent

    class FakeLLM:
        async def complete_json(self, system: str, user: str, **kwargs):
            return {
                "text": "胸训排好了",
                "card": {"card_type": "training_draft", "title": "胸训", "items": items},
            }

    async def fake_rewrite(text: str, **_kwargs):
        return Intent(
            expert="training",
            muscles=["胸"],
            raw=text,
            params={"topic": "plan", "agent": "coach_plan", "ready": True},
        )

    monkeypatch.setattr(graph_mod, "rewrite_intent", fake_rewrite)
    monkeypatch.setattr(graph_mod, "get_llm", lambda: FakeLLM())


def test_eval_thread_full_plan_produces_card_and_adopts(monkeypatch):
    """默认路径必须真出卡，采纳后组数按卡片上的 meta.sets 展开。

    这条挂了说明 cases-long.yaml 的 card / keeps_title / adopt 断言全部无从谈起。
    """
    from fastapi.testclient import TestClient

    from app.auth import require_token
    from app.main import app

    _patch_plan(
        monkeypatch,
        [
            {"id": "c1", "title": "哑铃卧推", "meta": {"sets": 4, "reps": "8-10", "muscle": "胸"}},
            {"id": "c2", "title": "上斜哑铃卧推", "meta": {"sets": 3, "reps": "8-10", "muscle": "胸"}},
            {"id": "c3", "title": "龙门架夹胸", "meta": {"sets": 3, "reps": "12", "muscle": "胸"}},
            {"id": "c4", "title": "绳索下压", "meta": {"sets": 3, "reps": "12", "muscle": "臂"}},
        ],
    )
    app.dependency_overrides[require_token] = lambda: "t"
    client = TestClient(app)
    res = client.post(
        "/api/eval/thread",
        headers={"Authorization": "Bearer t"},
        json={
            "turns": [{"text": "今天练胸"}],
            "profile": {"goal": "增肌", "experience": "进阶", "weight_kg": 70, "days_per_week": 4},
            "adopt_after": 1,
        },
    )
    app.dependency_overrides.clear()

    assert res.status_code == 200, res.text
    data = res.json()
    assert not data.get("error"), data

    turn = data["turns"][0]
    assert turn["route"] == "plan"
    assert turn["card_title"] == "胸训"
    assert turn["card_item_count"] == 4
    # 卡片 meta 要原样带出来，否则「组数都改成 4 组」这类断言没得测
    assert [it["meta"]["sets"] for it in turn["card_items_meta"]] == [4, 3, 3, 3]

    adopted = data["adopted"]
    assert adopted["status"] == "active"
    assert adopted["set_count"] == 13  # 4+3+3+3
    assert len(adopted["exercises"]) == 4


def test_eval_thread_short_circuit_produces_no_card(monkeypatch):
    """显式短路（short_circuit=True）只回路由说明：能验 route，但不出卡。"""
    from fastapi.testclient import TestClient

    from app.auth import require_token
    from app.main import app

    _patch_plan(monkeypatch, [])
    app.dependency_overrides[require_token] = lambda: "t"
    client = TestClient(app)
    res = client.post(
        "/api/eval/thread",
        headers={"Authorization": "Bearer t"},
        json={"turns": [{"text": "今天练胸"}], "short_circuit": True},
    )
    app.dependency_overrides.clear()

    assert res.status_code == 200, res.text
    turn = res.json()["turns"][0]
    assert turn["route"] == "plan"
    assert turn["card_title"] is None
    assert turn["card_item_count"] == 0
    assert turn["text_block"]  # eval_shortcut 的说明文案


def test_eval_thread_reports_missing_draft_when_adopting(monkeypatch):
    """指定了采纳却没有草稿时要说清楚，而不是静默返回 adopted=None。"""
    from fastapi.testclient import TestClient

    from app.auth import require_token
    from app.main import app

    _patch_plan(monkeypatch, [])
    app.dependency_overrides[require_token] = lambda: "t"
    client = TestClient(app)
    res = client.post(
        "/api/eval/thread",
        headers={"Authorization": "Bearer t"},
        json={"turns": [{"text": "今天练胸"}], "short_circuit": True, "adopt_after": 1},
    )
    app.dependency_overrides.clear()

    assert res.status_code == 200, res.text
    assert "没有产出可采纳的卡片" in (res.json().get("error") or "")
