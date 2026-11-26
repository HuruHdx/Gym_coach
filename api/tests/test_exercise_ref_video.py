"""教练动作卡内联视频门控与封面取数。"""

from app.brain.knowledge_reply import _allow_inline_video
from app.brain.memory import Intent
from app.services.public_catalog import _looks_like_video


def _intent(**params):
    return Intent(expert="chat", muscles=[], raw="q", params=dict(params))


def test_allow_inline_video_kb_single_hit():
    grounding = {
        "branch": "kb",
        "kb": {"hits": [{"id": "1", "name": "卧推"}], "near_miss": []},
    }
    assert _allow_inline_video(grounding, _intent()) is True


def test_allow_inline_video_blocked_by_near_miss():
    grounding = {
        "branch": "kb",
        "kb": {"hits": [{"id": "1"}], "near_miss": [{"id": "2"}]},
    }
    assert _allow_inline_video(grounding, _intent()) is False


def test_allow_inline_video_blocked_by_qa_kind():
    grounding = {
        "branch": "kb",
        "kb": {"hits": [{"id": "1"}], "near_miss": []},
    }
    for kind in ("decide", "recall", "compare"):
        assert _allow_inline_video(grounding, _intent(qa_kind=kind)) is False


def test_allow_inline_video_blocked_by_ask_branch():
    grounding = {
        "branch": "ask",
        "kb": {"hits": [{"id": "1"}], "near_miss": []},
    }
    assert _allow_inline_video(grounding, _intent()) is False


def test_looks_like_video():
    assert _looks_like_video("/static/exercises/custom/1/demo_x.mp4")
    assert _looks_like_video("https://cdn.example/a.webm?token=1")
    assert not _looks_like_video("/static/exercises/custom/1/start_x.jpg")
    assert not _looks_like_video(None)
