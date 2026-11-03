"""记忆评测集。

跑法（在 api 目录）：

    uv run pytest tests/test_memory_eval.py -q

这些用例不调用真实大模型，锁的是提示词里有没有带对记忆、以及档案写入规则。
页面上怎么对照，见每个测试的说明。
"""

from datetime import date, timedelta

from sqlmodel import Session, SQLModel, create_engine, select

from app.brain.memory_context import (
    _as_dict,
    _suggestions,
    build_intent_context,
    build_worker_context,
    load_conversation_messages,
    save_exchange,
    start_new_conversation,
)
from app.brain.memory_write import apply_user_memory
from app.models import ChatTurn, Goal, PendingMemory, Profile, ProfileHistory


def _db() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(Profile(goal=Goal.BULK, weight_kg=72, injuries=[]))
    session.commit()
    return session


def test_today_prompt_skips_yesterday_chat():
    """平常排课不带昨天的聊天。页面：昨天聊过划船机，今天只说「练胸」，调试里的用户消息不应出现昨天那句。"""
    session = _db()
    session.add(
        ChatTurn(
            session_day=date.today(),
            role="user",
            text="今天早些时候说过练肩",
        )
    )
    session.add(
        ChatTurn(
            session_day=date.today() - timedelta(days=1),
            role="user",
            text="昨天专门说过健身房没有划船机",
        )
    )
    session.commit()
    prompt = build_worker_context(
        session,
        "今天练胸",
        history=[{"role": "user", "text": "这条请求历史不该盖过库"}],
        draft_title=None,
        draft_items=None,
        long_term_block="【长期记忆】\n档案：长期目标：增肌",
        intent_line="课型=抗阻；部位=胸",
    )
    session.close()
    assert "昨天专门说过" not in prompt
    assert "这条请求历史不该盖过库" not in prompt
    assert "今天早些时候说过练肩" in prompt
    assert "【长期记忆】" in prompt
    assert "【短期记忆】" in prompt
    assert "【当前输入】" in prompt
    assert "用户本句：今天练胸" in prompt
    assert "学员属性怎么用" not in prompt
    assert "当前屏幕上的草稿" not in prompt


def test_past_chat_is_retrieved_when_user_points_at_it():
    """用户点明昨天，才回捞近三天。页面：说「昨天你说过什么」，调试里应出现【更早会话】。"""
    session = _db()
    session.add(
        ChatTurn(
            session_day=date.today() - timedelta(days=1),
            role="assistant",
            text="这家店先别排划船机",
            card_title="有氧",
            card_items=["跑步", "划船机"],
        )
    )
    session.commit()
    prompt = build_worker_context(
        session,
        "昨天你说过哪张卡里有划船机",
        history=None,
        draft_title=None,
        draft_items=None,
        long_term_block="【长期记忆】\n档案：长期目标：增肌",
        intent_line="",
    )
    session.close()
    assert "【更早会话】" in prompt
    assert "这家店先别排划船机" in prompt
    assert "划船机" in prompt


def test_live_plan_sits_inside_short_term_memory():
    """当前计划嵌在短期记忆里，不再单独写一块草稿指令。"""
    session = _db()
    prompt = build_worker_context(
        session,
        "不行健身房没有划船机呢",
        history=[
            {"role": "user", "text": "今天做有氧"},
            {"role": "assistant", "text": "排好了", "card_title": "有氧", "card_items": ["跑步"]},
        ],
        draft_title="有氧",
        draft_items=[
            {"title": "跑步", "selected": True, "meta": {"reps": "20分钟"}},
            {"title": "划船机", "selected": True, "meta": {"reps": "15分钟"}},
        ],
        long_term_block="【长期记忆】\n档案：无",
        intent_line="排除动作=划船机",
    )
    session.close()
    assert "计划《有氧》" in prompt
    assert "[勾选] 划船机" in prompt
    assert "意图：排除动作=划船机" in prompt
    assert prompt.index("【长期记忆】") < prompt.index("【短期记忆】") < prompt.index("【当前输入】")


def test_intent_context_can_omit_profile():
    """意图改写不看档案；反问节点仍可以带长期记忆。"""
    session = _db()
    hidden = build_intent_context(
        session,
        "今天练腿",
        history=None,
        draft_title=None,
        draft_items=None,
        profile=session.exec(select(Profile)).first(),
        include_profile=False,
    )
    shown = build_intent_context(
        session,
        "今天练腿",
        history=None,
        draft_title=None,
        draft_items=None,
        profile=session.exec(select(Profile)).first(),
    )
    session.close()
    assert "【长期记忆】" not in hidden
    assert "长期目标" not in hidden
    assert "用户本句：今天练腿" in hidden
    assert "【长期记忆】" in shown
    assert "长期目标：增肌" in shown


def test_text_json_columns_stay_structured():
    """card/suggestions 若以 JSON 文本读出，不能按字符拆成一堆空按钮。"""
    raw = '[{"label": "练胸肩三头", "prompt": "今天换成练胸肩三头"}]'
    assert _suggestions(raw) == [{"label": "练胸肩三头", "prompt": "今天换成练胸肩三头"}]
    assert _suggestions("null") == []
    assert _suggestions([{"label": "全身", "prompt": "今天全身"}]) == [
        {"label": "全身", "prompt": "今天全身"}
    ]
    card = _as_dict(
        '{"kind":"card","card_type":"training_draft","title":"腿+核心","items":[{"title":"深蹲"}]}'
    )
    assert card is not None
    assert card["title"] == "腿+核心"
    assert _as_dict("null") is None
    assert _as_dict(None) is None


def test_exchange_is_appended_not_overwritten():
    session = _db()
    save_exchange(session, "今天练胸", [{"kind": "text", "text": "先练胸"}, {"kind": "card", "title": "胸训", "items": [{"title": "哑铃卧推"}]}])
    save_exchange(session, "再加一组", [{"kind": "text", "text": "加上了"}])
    rows = session.exec(select(ChatTurn).order_by(ChatTurn.id)).all()
    session.close()
    assert [row.role for row in rows] == ["user", "assistant", "user", "assistant"]
    assert rows[1].card_title == "胸训"
    assert rows[1].card_items == ["哑铃卧推"]
    assert rows[0].conversation_id and rows[0].conversation_id == rows[1].conversation_id


def test_new_conversation_keeps_old_turns_out_of_short_term():
    """新对话后短期记忆不再带上一段；库里旧轮次仍在。"""
    session = _db()
    save_exchange(
        session,
        "今天练胸",
        [{"kind": "text", "text": "先练胸"}, {"kind": "card", "title": "胸训", "items": [{"title": "哑铃卧推"}]}],
    )
    old = load_conversation_messages(session)
    assert any("练胸" in (m.get("text") or "") for m in old["messages"])
    start_new_conversation(session)
    fresh = load_conversation_messages(session)
    assert fresh["messages"] == []
    assert fresh["conversation_id"] != old["conversation_id"]
    prompt = build_worker_context(
        session,
        "今天做有氧",
        history=None,
        draft_title=None,
        draft_items=None,
        long_term_block="【长期记忆】\n档案：无",
        intent_line="",
    )
    all_rows = session.exec(select(ChatTurn)).all()
    session.close()
    assert "先练胸" not in prompt
    assert "本段对话还没有更早的内容" in prompt or "短期记忆" in prompt
    assert len(all_rows) == 2



def test_injury_merges_once_and_can_be_removed():
    session = _db()
    first = apply_user_memory(session, "最近膝盖疼，练腿注意点")
    second = apply_user_memory(session, "膝盖还是有点疼")
    profile = session.exec(select(Profile).limit(1)).one()
    assert profile.injuries == ["膝盖"]
    assert "已记上伤痛：膝盖" in first.note
    assert second.note == ""
    apply_user_memory(session, "膝盖好了")
    profile = session.exec(select(Profile).limit(1)).one()
    session.close()
    assert profile.injuries == []


def test_today_missing_equipment_does_not_enter_profile():
    session = _db()
    effect = apply_user_memory(session, "不行健身房没有划船机呢")
    profile = session.exec(select(Profile).limit(1)).one()
    session.close()
    assert profile.avoid_exercises in (None, [])
    assert effect.applied == []


def test_standing_avoid_is_saved():
    session = _db()
    effect = apply_user_memory(session, "我们健身房没有划船机，以后别排")
    profile = session.exec(select(Profile).limit(1)).one()
    session.close()
    assert profile.avoid_exercises == ["划船(划船机)"]
    assert "以后避开：划船(划船机)" in effect.note


def test_weight_change_asks_then_confirms():
    """单值不直接覆盖。页面：说「我现在80公斤」，应先问；下一条回「要」才改档案。"""
    session = _db()
    asked = apply_user_memory(session, "我现在80公斤了")
    profile = session.exec(select(Profile).limit(1)).one()
    assert profile.weight_kg == 72
    assert "要改成 80kg 吗" in asked.note
    assert session.exec(select(PendingMemory)).first() is not None
    done = apply_user_memory(session, "要")
    profile = session.exec(select(Profile).limit(1)).one()
    history = session.exec(select(ProfileHistory).where(ProfileHistory.field == "weight_kg")).all()
    session.close()
    assert profile.weight_kg == 80
    assert "已把体重更新为 80" in done.note
    assert history[-1].new_value == "80"


def test_weight_change_can_be_dismissed():
    session = _db()
    apply_user_memory(session, "体重改到 80kg")
    effect = apply_user_memory(session, "不用改")
    profile = session.exec(select(Profile).limit(1)).one()
    session.close()
    assert profile.weight_kg == 72
    assert "先不改档案" in effect.note


def test_goal_word_in_a_workout_request_does_not_overwrite_profile():
    session = _db()
    apply_user_memory(session, "今天做减脂有氧")
    profile = session.exec(select(Profile).limit(1)).one()
    pending = session.exec(select(PendingMemory)).first()
    session.close()
    assert profile.goal == Goal.BULK
    assert pending is None
