from datetime import date

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.brain.feedback import submit_feedback
from app.models import (
    ActiveChat,
    ChatTurn,
    DebugTrace,
    Experience,
    FeedbackEvent,
    Goal,
    Profile,
)
from app.schemas import FeedbackRequest


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_downvote_captures_snapshot_from_trace():
    session = _session()
    session.add(Profile(goal=Goal.BULK, experience=Experience.NOVICE, weight_kg=70))
    session.add(ActiveChat(conversation_id="c1"))
    session.add(
        ChatTurn(
            conversation_id="c1",
            session_day=date.today(),
            role="user",
            text="深蹲怎么做",
        )
    )
    session.add(
        ChatTurn(
            conversation_id="c1",
            session_day=date.today(),
            role="assistant",
            text="深蹲要保持膝盖朝脚尖方向。",
        )
    )
    session.add(
        DebugTrace(
            user_text="深蹲怎么做",
            payload={
                "graph": {"route": "chat", "steps": []},
                "intent": {
                    "muscles": ["腿"],
                    "params": {
                        "agent": "coach_chat",
                        "topic": "qa",
                        "domain": "training",
                        "rewrite": "问深蹲做法",
                    },
                },
                "grounding": {
                    "branch": "knowledge",
                    "kb": {"queried": True, "hit": False, "reason": "class"},
                    "citations": [],
                },
                "blocks": [{"kind": "text", "text": "深蹲要保持膝盖朝脚尖方向。"}],
            },
        )
    )
    session.commit()
    trace = session.exec(select(DebugTrace)).first()
    assert trace is not None and trace.id is not None

    event = submit_feedback(
        session,
        FeedbackRequest(
            rating="down",
            tags=["bad_answer"],
            note="答非所问",
            trace_id=trace.id,
        ),
    )
    assert event.id is not None
    assert event.rating == "down"
    assert event.tags == ["bad_answer"]
    assert event.note == "答非所问"
    assert event.question == "深蹲怎么做"
    assert "膝盖" in event.answer
    assert event.export_status == "pending"
    snap = event.snapshot or {}
    assert snap.get("route") == "chat"
    assert snap.get("branch") == "knowledge"
    assert snap.get("intent", {}).get("topic") == "qa"
    assert snap.get("profile", {}).get("goal") == "增肌"

    again = submit_feedback(
        session,
        FeedbackRequest(rating="up", tags=[], note="", trace_id=trace.id),
    )
    assert again.id == event.id
    assert again.rating == "up"
    assert again.export_status == "discarded"
    assert len(session.exec(select(FeedbackEvent)).all()) == 1
    session.close()


def test_downvote_requires_tag():
    session = _session()
    session.add(DebugTrace(user_text="你好", payload={"blocks": [{"kind": "text", "text": "你好"}]}))
    session.commit()
    trace = session.exec(select(DebugTrace)).first()
    assert trace is not None and trace.id is not None
    try:
        submit_feedback(session, FeedbackRequest(rating="down", tags=[], trace_id=trace.id))
        raised = False
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 400
    assert raised
    session.close()


def _load_export_mod():
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "export_feedback_inbox.py"
    spec = importlib.util.spec_from_file_location("export_feedback_inbox", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_export_inbox_writes_yaml(tmp_path):
    session = _session()
    session.add(
        FeedbackEvent(
            rating="down",
            tags=["bad_answer"],
            note="胡编",
            question="深蹲怎么做",
            answer="随便说说",
            snapshot={
                "intent": {"topic": "qa", "domain": "training"},
                "route": "chat",
                "branch": "knowledge",
                "profile": {"goal": "增肌", "experience": "新手", "weight_kg": 70},
                "history": [],
            },
            export_status="pending",
        )
    )
    session.commit()

    mod = _load_export_mod()
    doc = mod._case_doc(session.exec(select(FeedbackEvent)).first(), format="single")
    text = mod._dump_yaml(doc)
    assert "FB-" in doc["description"]
    assert "深蹲怎么做" in text
    assert "bad_answer" in text
    assert "file://assertions/shape.js" in text
    assert doc["meta"]["format"] == "single"
    session.close()


def test_export_inbox_auto_thread_when_multi_user_turns():
    session = _session()
    session.add(
        FeedbackEvent(
            rating="down",
            tags=["multi_turn_lost"],
            note="忘了上一轮",
            conversation_id="c-long",
            question="那深蹲呢",
            answer="嗯随便",
            snapshot={
                "intent": {"topic": "qa", "domain": "training"},
                "route": "chat",
                "branch": "knowledge",
                "history": [
                    {"role": "user", "text": "卧推怎么做"},
                    {"role": "assistant", "text": "肩胛收紧。"},
                ],
                "profile": {"goal": "增肌", "experience": "进阶"},
            },
            export_status="pending",
        )
    )
    session.add(
        ChatTurn(
            conversation_id="c-long",
            session_day=date.today(),
            role="user",
            text="卧推怎么做",
        )
    )
    session.add(
        ChatTurn(
            conversation_id="c-long",
            session_day=date.today(),
            role="assistant",
            text="肩胛收紧。",
        )
    )
    session.add(
        ChatTurn(
            conversation_id="c-long",
            session_day=date.today(),
            role="user",
            text="那深蹲呢",
        )
    )
    session.commit()

    mod = _load_export_mod()
    row = session.exec(select(FeedbackEvent)).first()
    doc = mod._case_doc(row, format="auto", session=session)
    assert doc["meta"]["format"] == "thread"
    assert doc["vars"]["thread"]["turns"] == ["卧推怎么做", "那深蹲呢"]
    assert "file://assertions/shape-long.js" in mod._dump_yaml(doc)
    session.close()


def test_chat_turn_persists_trace_id_for_reload():
    from app.brain.memory_context import load_conversation_messages, save_exchange

    session = _session()
    session.add(ActiveChat(conversation_id="c-trace"))
    session.add(DebugTrace(user_text="深蹲怎么做", payload={}))
    session.commit()
    trace = session.exec(select(DebugTrace)).first()
    assert trace is not None and trace.id is not None

    turn_id = save_exchange(
        session,
        "深蹲怎么做",
        [{"kind": "text", "text": "膝盖朝脚尖。"}],
        trace_id=trace.id,
    )
    assert turn_id is not None
    stored = session.get(ChatTurn, turn_id)
    assert stored is not None
    assert stored.trace_id == trace.id

    payload = load_conversation_messages(session, "c-trace")
    assistant = [m for m in payload["messages"] if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["trace_id"] == trace.id
    assert assistant[0]["turn_id"] == turn_id
    session.close()
