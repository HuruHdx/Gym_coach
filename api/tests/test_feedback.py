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


def test_export_inbox_writes_yaml(tmp_path):
    import importlib.util
    from pathlib import Path

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

    script = Path(__file__).resolve().parents[1] / "scripts" / "export_feedback_inbox.py"
    spec = importlib.util.spec_from_file_location("export_feedback_inbox", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # 脚本默认连 app.db.engine；这里改用内存会话写文件后只测 _case_doc / dump
    doc = mod._case_doc(session.exec(select(FeedbackEvent)).first())
    text = mod._dump_yaml(doc)
    assert "FB-" in doc["description"]
    assert "深蹲怎么做" in text
    assert "bad_answer" in text
    assert "file://assertions/shape.js" in text
    session.close()
