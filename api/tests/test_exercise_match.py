"""口播匹配：含糊枚举、百分制、不大类硬比。"""

from __future__ import annotations

from app.exercise_match import (
    decompose_spoken_name,
    is_ambiguous_spoken,
    normalize_spoken_name,
    suggest_asr_repair,
)
from app.services.studio_service import _keep_snippets_on_own_action, _snippet_for_name


def test_normalize_strips_fillers():
    assert "标准" not in normalize_spoken_name("标准杠铃深蹲教程")
    assert normalize_spoken_name("平卧推") == "平板推"


def test_decompose_barbell_bench():
    parts = decompose_spoken_name("上斜杠铃卧推")
    assert parts["core"] == "卧推"
    assert parts["implement"] == "杠铃"
    assert "上斜" in parts["variant"]


def test_asr_repair_only_when_unique():
    assert suggest_asr_repair("载剧下拉", ["窄距下拉", "高位下拉", "坐姿划船"]) == "窄距下拉"
    assert suggest_asr_repair("窄距下拉", ["窄距下拉"]) is None
    assert suggest_asr_repair("载剧下拉", ["窄距下拉", "载距下拉"]) is None
    assert suggest_asr_repair("今天练背", ["窄距下拉"]) is None


def test_snippet_starts_at_this_action_not_the_previous():
    segments = [
        {"start": 25.48, "end": 27.0, "text": "每组十到十二次"},
        {"start": 27.16, "end": 28.1, "text": "第三个动作"},
        {"start": 28.20, "end": 29.5, "text": "载剧下拉"},
        {"start": 29.60, "end": 31.0, "text": "针对大小圆后束"},
        {"start": 32.08, "end": 33.2, "text": "注意动作细节"},
        {"start": 39.92, "end": 41.0, "text": "收尾动作"},
    ]
    snip = _snippet_for_name(segments, "载剧下拉")
    assert snip is not None
    assert snip["start"] == 28.2
    assert snip["start"] > 27.16
    assert snip["end"] < 39.92
    rows = [
        {"spoken_at": 15.0, "snippet": {"start": 14.0, "end": 26.0, "spoken_at": 15.0}},
        {"spoken_at": 28.2, "snippet": snip},
    ]
    _keep_snippets_on_own_action(rows)
    assert rows[0]["snippet"]["start"] >= 15.0
    assert rows[0]["snippet"]["end"] <= 28.2
    assert rows[1]["snippet"]["start"] >= 28.2


def test_ambiguous_bare_names():
    assert is_ambiguous_spoken("深蹲")
    assert is_ambiguous_spoken("硬拉")
    assert is_ambiguous_spoken("卧推")
    assert not is_ambiguous_spoken("杠铃深蹲")
    assert not is_ambiguous_spoken("罗马尼亚硬拉")
