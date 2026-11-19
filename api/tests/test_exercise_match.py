"""口播匹配：含糊枚举、百分制、不大类硬比。"""

from __future__ import annotations

from app.exercise_match import (
    decompose_spoken_name,
    is_ambiguous_spoken,
    normalize_spoken_name,
)


def test_normalize_strips_fillers():
    assert "标准" not in normalize_spoken_name("标准杠铃深蹲教程")
    assert normalize_spoken_name("平卧推") == "平板推"


def test_decompose_barbell_bench():
    parts = decompose_spoken_name("上斜杠铃卧推")
    assert parts["core"] == "卧推"
    assert parts["implement"] == "杠铃"
    assert "上斜" in parts["variant"]


def test_ambiguous_bare_names():
    assert is_ambiguous_spoken("深蹲")
    assert is_ambiguous_spoken("硬拉")
    assert is_ambiguous_spoken("卧推")
    assert not is_ambiguous_spoken("杠铃深蹲")
    assert not is_ambiguous_spoken("罗马尼亚硬拉")
