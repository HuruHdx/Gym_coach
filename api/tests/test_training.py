from app.brain.validate import validate_and_build_blocks
from app.exercises_catalog import alternatives, is_banned_for_injuries
from app.models import TrainingSetLog
from app.services.session_service import minutes_from_seconds, ordered_sets


def test_exercise_order_beats_alphabetical_name():
    rows = [
        TrainingSetLog(id=1, session_id=1, exercise_name="腿举", set_index=1, exercise_order=2),
        TrainingSetLog(id=2, session_id=1, exercise_name="杠铃深蹲", set_index=1, exercise_order=1),
        TrainingSetLog(id=3, session_id=1, exercise_name="杠铃深蹲", set_index=2, exercise_order=1),
    ]
    assert [row.exercise_name for row in ordered_sets(rows)] == ["杠铃深蹲", "杠铃深蹲", "腿举"]


def test_legacy_sets_keep_insert_order():
    rows = [
        TrainingSetLog(id=10, session_id=1, exercise_name="腿举", set_index=1, exercise_order=0),
        TrainingSetLog(id=11, session_id=1, exercise_name="杠铃深蹲", set_index=1, exercise_order=0),
        TrainingSetLog(id=12, session_id=1, exercise_name="腿举", set_index=2, exercise_order=0),
    ]
    assert [row.exercise_name for row in ordered_sets(rows)] == ["腿举", "腿举", "杠铃深蹲"]


def test_minutes_from_seconds_rounds_for_calories():
    assert minutes_from_seconds(0) is None
    assert minutes_from_seconds(45) == 1
    assert minutes_from_seconds(42 * 60) == 42
    assert minutes_from_seconds(90) == 2


def test_injury_bans_deadlift_for_waist():
    assert is_banned_for_injuries("硬拉", ["腰"])
    assert is_banned_for_injuries("杠铃深蹲", ["膝盖"])
    assert not is_banned_for_injuries("哑铃卧推", ["腰"])


def test_alternatives_excludes_banned():
    opts = alternatives("腿", injuries=["膝盖"])
    joined = "".join(opts)
    assert "深蹲" not in joined
    assert any("腿举" in o or "臀推" in o or "弯举" in o for o in opts)


def test_deadlift_shows_up_for_leg_role_swap():
    opts = alternatives("腿")
    assert "杠铃硬拉" in opts
    assert "杠铃罗马尼亚硬拉" in opts


def test_validate_subtitle_is_sets_not_coaching_cues():
    raw = {
        "text": "练胸",
        "card": {
            "card_type": "training_draft",
            "title": "胸训",
            "items": [
                {
                    "id": "1",
                    "title": "杠铃卧推",
                    "subtitle": "中胸 · 复合主项，脚踩实、肘约45度",
                    "meta": {"sets": 4, "reps": "8-10", "weight": 40, "muscle": "胸"},
                    "selected": True,
                }
            ],
        },
    }
    blocks = validate_and_build_blocks(raw, injuries=[])
    card = next(b for b in blocks if b.kind == "card")
    assert card.items[0].subtitle == "4×8-10 · 建议 40.0kg"
    assert "肘" not in (card.items[0].subtitle or "")


def test_named_deadlift_is_not_claimed_when_waist_drops_it():
    from app.brain.validate import reconcile_requested_injury_drop

    raw = {
        "text": "按你说的把硬拉加进来作为主打。",
        "card": {
            "card_type": "training_draft",
            "title": "硬拉",
            "items": [
                {"id": "1", "title": "杠铃硬拉", "meta": {"sets": 3, "reps": "6", "muscle": "腿"}, "selected": True},
                {"id": "2", "title": "滑车仰卧深蹲", "meta": {"sets": 3, "reps": "10-12", "muscle": "腿"}, "selected": True},
            ],
        },
    }
    blocks = validate_and_build_blocks(raw, ["腰"])
    blocks = reconcile_requested_injury_drop(
        blocks,
        raw="我想做硬拉",
        focus=["硬拉"],
        injuries=["腰"],
        previous_title="腿训",
    )
    text = next(block for block in blocks if block.kind == "text")
    card = next(block for block in blocks if block.kind == "card")
    titles = [item.title for item in card.items]
    assert "杠铃硬拉" not in titles
    assert "滑车仰卧深蹲" in titles
    assert card.title == "腿训"
    assert "加进来" not in text.text
    assert "这版不加" in text.text
    assert "臀桥" in text.text
    from app.brain.validate import injury_advice_suggestions

    tips = injury_advice_suggestions(["杠铃硬拉"], "我想做硬拉", ["硬拉"])
    assert tips == [{"label": "还是要硬拉", "prompt": "还是要硬拉"}]


def test_first_deadlift_ask_is_a_question_without_naming_it_in_the_safer_choice():
    from app.brain.validate import injury_confirm

    confirm = injury_confirm(["腰"], ["杠铃硬拉"], "我想练硬拉", ["硬拉"], "腿训")
    assert confirm["text"] == "腰有伤，硬拉负担比较大。要换成臀桥这类更轻的后链，还是仍按硬拉排？"
    safer, insist = confirm["suggestions"]
    assert safer["label"] == "换成臀桥"
    assert "更省" not in confirm["text"]
    assert "你有腰" not in confirm["text"]
    assert "硬拉" not in safer["prompt"]
    assert "臀桥" in safer["prompt"]
    assert insist["prompt"] == "还是要硬拉"


def test_behind_neck_press_is_asked_before_a_card_even_with_other_injuries():
    from app.brain.validate import injury_confirm, named_banned_exercises, user_insists

    names = named_banned_exercises("我想做颈后推举", [], ["肩", "腰"])
    assert names == ["颈后推举"]
    assert named_banned_exercises("今天练肩", [], ["肩"]) == []
    assert named_banned_exercises("不要颈后推举", [], ["肩"]) == []
    assert named_banned_exercises("我想练硬拉", ["硬拉"], ["腰"]) == ["杠铃硬拉"]
    confirm = injury_confirm(["肩", "腰"], names, "我想做颈后推举", [], None)
    assert confirm["text"] == "肩有伤，颈后推举负担比较大。要换成不过头的推举，还是仍按颈后推举排？"
    safer = confirm["suggestions"][0]["prompt"]
    assert "颈后" not in safer
    assert named_banned_exercises(safer, [], ["肩", "腰"]) == []
    assert user_insists("还是要颈后推举", None, names)
    # 库里没有的名字不单独写死，点名后同样先问
    unknown = named_banned_exercises("我想做水晶龙卷风", ["水晶龙卷风"], ["肩"])
    assert unknown == ["水晶龙卷风"]
    assert named_banned_exercises("不要水晶龙卷风", ["水晶龙卷风"], ["肩"]) == []
    assert named_banned_exercises("我想做卧推", ["卧推"], ["肩"]) == []
    other = injury_confirm(["肩", "腰"], unknown, "我想做水晶龙卷风", ["水晶龙卷风"], None)
    assert other["text"].startswith("肩有伤、腰有伤，水晶龙卷风")
    assert "臀桥" not in other["text"]
    assert "更轻的同类" in other["text"]


def test_knee_intensity_raise_is_advice_until_they_insist():
    from app.brain.validate import intensity_advice, is_intensity_raise, user_demands_heavier

    assert is_intensity_raise("强度太低了 给我加点")
    assert not user_demands_heavier("强度太低了 给我加点", None)
    advice = intensity_advice(["膝盖"])
    assert advice["text"] == (
        "膝盖有伤，不建议把重量加大或做到接近力竭。"
        "如果你还是要求加重，那就按大重量、低次数改，不适就停。"
    )
    assert advice["suggestions"] == [{"label": "还是要加重", "prompt": "还是要加重"}]
    assert user_demands_heavier("还是要加重", [{"role": "assistant", "text": advice["text"]}])
    assert user_demands_heavier("给我加点", [{"role": "assistant", "text": advice["text"]}])


def test_revision_keeps_weights_from_the_previous_card():
    from app.brain.validate import carry_forward_weights, validate_and_build_blocks

    previous = [
        {"title": "杠铃卧推", "meta": {"sets": 4, "reps": "6-8", "weight": 60, "muscle": "胸"}},
        {"title": "杠铃上斜卧推", "meta": {"sets": 4, "reps": "8-10", "weight": 45, "muscle": "胸"}},
        {"title": "杠杆下斜推胸v.2", "meta": {"sets": 3, "reps": "10-12", "weight": 50, "muscle": "胸"}},
        {"title": "双杠深俯卧撑", "meta": {"sets": 3, "reps": "8-12", "muscle": "胸"}},
    ]
    raw = {
        "text": "换成上斜。",
        "card": {
            "card_type": "training_draft",
            "title": "胸训",
            "items": [
                {"id": "1", "title": "杠铃上斜卧推", "meta": {"sets": 4, "reps": "6-8", "muscle": "胸"}, "selected": True},
                {"id": "2", "title": "杠铃上斜卧推", "meta": {"sets": 3, "reps": "8-10", "muscle": "胸"}, "selected": True},
                {"id": "3", "title": "杠杆下斜推胸v.2", "meta": {"sets": 3, "reps": "10-12", "muscle": "胸"}, "selected": True},
                {"id": "4", "title": "双杠深俯卧撑", "meta": {"sets": 3, "reps": "8-12", "muscle": "胸"}, "selected": True},
            ],
        },
    }
    blocks = carry_forward_weights(validate_and_build_blocks(raw, []), previous)
    card = next(block for block in blocks if block.kind == "card")
    weights = [item.meta.get("weight") for item in card.items]
    assert weights[0] == 60
    assert weights[1] == 45
    assert weights[2] == 50
    assert card.items[3].meta.get("weight") is None


def test_insisted_deadlift_stays_on_the_card():
    from app.brain.validate import apply_injury_insist, user_insists

    raw = {
        "text": "按你说的把硬拉加进来。",
        "card": {
            "card_type": "training_draft",
            "title": "硬拉",
            "items": [
                {"id": "1", "title": "杠铃硬拉", "meta": {"sets": 3, "reps": "5", "muscle": "腿"}, "selected": True},
                {"id": "2", "title": "滑车仰卧深蹲", "meta": {"sets": 3, "reps": "10", "muscle": "腿"}, "selected": True},
            ],
        },
    }
    assert user_insists("还是要硬拉", None, ["杠铃硬拉"])
    assert user_insists(
        "我想做硬拉",
        [{"role": "assistant", "text": "腰伤做硬拉负担大，这版不加。"}],
        ["杠铃硬拉"],
    )
    assert user_insists(
        "我想练硬拉",
        [{"role": "assistant", "text": "你有腰，硬拉对这里负担比较大。这版换成更省的做法，还是仍按硬拉排？"}],
        ["杠铃硬拉"],
    )
    assert not user_insists("我想做硬拉", None, ["杠铃硬拉"])
    blocks = validate_and_build_blocks(raw, ["腰"], allow=["杠铃硬拉"])
    blocks = apply_injury_insist(
        blocks,
        names=["杠铃硬拉"],
        injuries=["腰"],
        raw="还是要硬拉",
        focus=["硬拉"],
        muscle="腿",
    )
    text = next(block for block in blocks if block.kind == "text")
    card = next(block for block in blocks if block.kind == "card")
    assert any(item.title == "杠铃硬拉" for item in card.items)
    assert "按你的要求排了硬拉" in text.text
    assert "不舒服就停" in text.text


def test_validate_drops_banned_items():
    raw = {
        "text": "练腿",
        "card": {
            "card_type": "training_draft",
            "title": "腿训",
            "items": [
                {"id": "1", "title": "硬拉", "meta": {"sets": 3, "reps": "5", "weight": 80, "muscle": "腿"}, "selected": True},
                {"id": "2", "title": "滑车45度腿举", "meta": {"sets": 4, "reps": "10", "weight": 100, "muscle": "腿"}, "selected": True},
            ],
        },
    }
    blocks = validate_and_build_blocks(raw, injuries=["腰"])
    card = next(b for b in blocks if b.kind == "card")
    titles = [i.title for i in card.items]
    assert "硬拉" not in titles and "杠铃硬拉" not in titles
    assert "滑车45度腿举" in titles
