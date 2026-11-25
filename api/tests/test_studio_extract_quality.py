"""工坊抽取质量：scene 过滤、evidence 直取锚点、局部合并、可疑标记。"""

from __future__ import annotations

from app.services.studio_service import (
    _DROP_SCENES,
    _apply_structure_suspect,
    _format_segment_lines,
    _keep_snippets_on_own_action,
    _llm_item_teach_score,
    _mark_overlap_suspects,
    _merge_llm_blocks,
    _snippet_from_evidence_seg,
    _snippet_for_name,
)


def test_format_segment_lines_uses_global_index():
    segs = [
        {"_idx": 41, "start": 72.0, "end": 74.0, "text": "下一个动作高位下拉"},
        {"_idx": 42, "start": 75.0, "end": 77.0, "text": "四组八到十次"},
    ]
    body = _format_segment_lines(segs)
    assert "[#41 01:12]" in body
    assert "[#42 01:15]" in body


def test_snippet_from_evidence_seg_ignores_name_rescan():
    segments = [
        {"start": 10.0, "end": 12.0, "text": "今天安排杠铃卧推和夹胸"},
        {"start": 60.0, "end": 62.0, "text": "正式组杠铃卧推四组"},
        {"start": 90.0, "end": 92.0, "text": "夹胸三组"},
    ]
    snip = _snippet_from_evidence_seg(segments, 1)
    assert snip is not None
    assert snip["spoken_at"] == 60.0
    # 降级子串仍可用，但不该被 evidence 路径调用覆盖
    name_hit = _snippet_for_name(segments, "杠铃卧推")
    assert name_hit is not None


def test_merge_allows_distant_same_name_and_drops_example_scene():
    blocks = [
        {
            "block_title": "热身",
            "target_muscle": "肩",
            "exercises": [
                {"spoken_name": "面拉", "scene": "warmup", "spoken_at": 20, "cues": []},
            ],
        },
        {
            "block_title": "肩",
            "target_muscle": "肩",
            "exercises": [
                {
                    "spoken_name": "面拉",
                    "scene": "teaching",
                    "spoken_at": 200,
                    "target_sets": 3,
                    "cues": [{"text": "肘高", "source_at": 205}],
                    "evidence_seg": 10,
                },
                {
                    "spoken_name": "侧平举",
                    "scene": "example",
                    "spoken_at": 40,
                    "evidence_text": "不适可以靠侧平举改善",
                },
            ],
        },
    ]
    merged = _merge_llm_blocks(blocks)
    names = [ex["spoken_name"] for b in merged for ex in b["exercises"]]
    assert names.count("面拉") == 2
    assert "侧平举" not in names


def test_teach_score_no_late_bias():
    early = {
        "scene": "teaching",
        "spoken_at": 30,
        "target_sets": 4,
        "cues": [{"text": "a"}],
        "evidence_seg": 1,
    }
    late_recallish = {
        "scene": "teaching",
        "spoken_at": 900,
        "cues": [],
        "evidence_seg": 90,
    }
    assert _llm_item_teach_score(early) > _llm_item_teach_score(late_recallish)


def test_structure_suspect_and_overlap():
    row = {
        "role": "main",
        "scene": "teaching",
        "evidence": None,
        "cues": [],
        "mistakes": [],
        "sets_from_transcript": False,
    }
    _apply_structure_suspect(row)
    assert row["suspect"] is True
    assert row["suspect_reason"] == "missing_evidence"

    warmup = {
        "role": "warmup",
        "scene": "warmup",
        "evidence": {"text": "热身面拉", "start": 1, "end": 5},
        "cues": [],
        "sets_from_transcript": False,
    }
    _apply_structure_suspect(warmup)
    assert not warmup.get("suspect")

    rows = [
        {"spoken_at": 10.0, "snippet": {"start": 10.0, "end": 18.0, "spoken_at": 10.0}},
        {"spoken_at": 15.0, "snippet": {"start": 15.0, "end": 22.0, "spoken_at": 15.0}},
    ]
    _keep_snippets_on_own_action(rows)
    _mark_overlap_suspects(rows)
    # 裁切后若仍重叠会标；至少时间单调
    assert rows[0]["snippet"]["end"] <= rows[1]["snippet"]["start"] + 0.15 or rows[0].get("suspect")


def test_drop_scenes_constant():
    assert "example" in _DROP_SCENES
    assert "intro" in _DROP_SCENES
