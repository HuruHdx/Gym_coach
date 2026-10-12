from app.taxonomy import canonicalize_exercise, normalize_muscle, Muscle
from app.brain.memory import parse_intent


def test_canonicalize():
    assert canonicalize_exercise("哑铃平板卧推") == "哑铃卧推"
    assert canonicalize_exercise(" 哑铃卧推 ") == "哑铃卧推"


def test_normalize_muscle():
    assert normalize_muscle("今天练胸") == Muscle.CHEST
    assert normalize_muscle("练背") == Muscle.BACK


def test_parse_intent_training():
    i = parse_intent("今天练胸，安排几个动作")
    assert i.expert == "training"
    assert "胸" in i.muscles


def test_parse_intent_upper_lower_body():
    upper = parse_intent("今天练上半身")
    assert upper.expert == "training"
    assert set(upper.muscles) == {"胸", "背", "肩"}
    assert upper.params.get("split") == "上半身"

    lower = parse_intent("下半身随便搞搞")
    assert set(lower.muscles) == {"腿", "核心"}
    assert lower.params.get("flexible") is True


def test_parse_intent_push_pull_day():
    push = parse_intent("今天推日安排一下")
    assert set(push.muscles) == {"胸", "肩", "臂"}
    pull = parse_intent("拉日练什么")
    assert set(pull.muscles) == {"背", "臂"}
    # 勿把「卧推」误判成推日
    chest = parse_intent("今天练胸，安排哑铃卧推")
    assert chest.muscles == ["胸"]
    assert "split" not in chest.params


def test_parse_intent_equipment_and_fatigue():
    hotel = parse_intent("出差酒店随便练练")
    assert hotel.params.get("equipment") == ["自重"]
    assert hotel.params.get("flexible") is True

    home = parse_intent("家里只有哑铃练胸")
    assert "自由重量" in home.params.get("equipment", [])
    assert "胸" in home.muscles

    tired = parse_intent("今天没劲了练背")
    assert tired.params.get("fatigue") is True
    assert tired.params.get("deload") is True
    assert "背" in tired.muscles
