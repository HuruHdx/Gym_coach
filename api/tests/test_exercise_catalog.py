"""openGym catalog mapping + retrieval."""

from app.exercise_mapping import map_gear, map_modality, map_muscle, map_roles
from app.exercises_catalog import (
    find_catalog_mentions_in_text,
    find_exercises_in_text,
    format_candidates_block,
    is_banned_for_injuries,
    looks_like_exercise_name,
    retrieve_candidates,
)


def test_map_muscle_and_modality():
    assert map_muscle("chest", "pectorals") == "胸"
    assert map_muscle("upper legs", "glutes") == "腿"
    assert map_muscle("waist", "abs") == "核心"
    assert map_modality("strength") == "抗阻"
    assert map_modality("cardio") == "有氧"
    assert map_modality("plyometrics") == "HIIT"
    assert map_modality("yoga") == "灵活性"
    assert map_gear("dumbbell") == "自由重量"
    assert map_gear("cable") == "绳索"
    assert map_gear("body weight") == "自重"
    assert map_gear("leverage machine") == "器械"


def test_deadlift_roles():
    assert "腿" in map_roles("barbell deadlift", "背")
    assert "背" in map_roles("barbell romanian deadlift", "腿")


def test_retrieve_candidates_respects_modality_and_injury():
    chest = retrieve_candidates(muscles=["胸"], modalities=["抗阻"], limit=20)
    assert chest
    assert all("胸" in (c.get("roles") or [c["muscle"]]) for c in chest)
    assert any(c.get("coach_core") for c in chest) or any("卧推" in c["name"] for c in chest)

    safe_legs = retrieve_candidates(muscles=["腿"], modalities=["抗阻"], injuries=["膝盖"], limit=20)
    joined = "".join(c["name"] for c in safe_legs)
    assert "深蹲" not in joined
    assert "跳跃" not in joined


def test_candidates_block_format():
    items = retrieve_candidates(muscles=["胸"], modalities=["抗阻"], limit=3)
    block = format_candidates_block(items)
    assert block.startswith("候选动作库：")
    assert "|" in block


def test_catalog_size_loaded():
    from app.exercises_catalog import EXERCISES_DATABASE, ensure_loaded

    ensure_loaded()
    assert len(EXERCISES_DATABASE) > 5000


def test_find_and_ban_smoke():
    # 排课不再做口语热词匹配
    assert find_exercises_in_text("今天杠铃卧推") == []
    assert is_banned_for_injuries("杠铃硬拉", ["腰"])
    assert not is_banned_for_injuries("哑铃卧推", ["腰"])


def test_catalog_mentions_for_memory_not_planning_hotwords():
    """库内子串命中只给档案/排除用；解剖标签不算动作。"""
    assert find_exercises_in_text("今天练腿，以杠铃深蹲为主") == []
    assert "划船(划船机)" in find_catalog_mentions_in_text("健身房没有划船机")
    assert not looks_like_exercise_name("股四头肌")
    assert looks_like_exercise_name("深蹲")


def test_retrieve_skips_anatomy_labels():
    cands = retrieve_candidates(muscles=["腿"], modalities=["抗阻"], focus=["股四头肌"], limit=20)
    names = [c["name"] for c in cands]
    assert "股四头肌" not in names
    assert any("深蹲" in n or "腿举" in n or "硬拉" in n for n in names)


def test_retrieve_shuffles_within_score_band():
    """同档候选应有随机性，不能每次锁死同一套。"""
    sets = []
    for _ in range(8):
        names = tuple(
            c["name"]
            for c in retrieve_candidates(muscles=["腿"], modalities=["抗阻"], limit=8)
        )
        sets.append(names)
    assert len(set(sets)) >= 2
