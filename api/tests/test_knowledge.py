"""知识库分支：不调用模型。"""

from app.brain.knowledge import ground_question


def test_exact_lever_row_is_upper_back():
    g = ground_question("杠杆坐姿划船练哪里")
    assert g.branch == "kb"
    assert g.reason == "exact_name"
    assert g.citations == ["1350"]
    assert g.hits[0]["target"] == "上背"
    assert "上背" in g.direct_answer
    assert "背阔肌" not in g.direct_answer


def test_squat_alias_uses_barbell_not_bodyweight():
    g = ground_question("深蹲练哪里")
    assert g.branch == "kb"
    assert g.reason == "canonical"
    assert "深蹲主要练股四头肌" in g.direct_answer
    assert "按杠铃" not in g.direct_answer
    assert g.citations == ["3593"]
    assert "1197" not in g.citations


def test_bench_alias():
    g = ground_question("卧推练哪里")
    assert g.citations == ["0025"]
    assert g.reason == "canonical"
    assert "胸大肌" in g.direct_answer


def test_deadlift_inside_injury_question_is_canonical():
    g = ground_question("我腰不好，硬拉能做吗")
    assert g.branch == "kb"
    assert g.reason == "canonical"
    assert g.citations == ["0032"]
    assert g.queried is True


def test_zuo_typo_hits_lever_seated_row():
    g = ground_question("杠杆座姿划船练哪里")
    assert g.branch == "kb"
    assert g.reason == "exact_name"
    assert g.citations == ["1350"]
    assert "上背" in g.direct_answer


def test_deadlift_alias_says_glutes():
    g = ground_question("硬拉练哪里")
    assert g.citations == ["0032"]
    assert "臀" in g.direct_answer
    assert "背阔肌" not in g.direct_answer
    # D-07：passage 给模型看协同/参与，不只主肌群
    assert "下背" in g.passage or "背" in g.passage
    assert "协同肌" in g.passage


def test_bench_passage_has_secondary():
    g = ground_question("卧推练哪里")
    assert "胸大肌" in g.passage
    assert "肱三头肌" in g.passage or "三角肌" in g.passage


def test_english_exact_name():
    g = ground_question("lever seated row 练哪里")
    assert g.branch == "kb"
    assert g.reason == "exact_name"
    assert g.citations == ["1350"]


def test_versioned_name_keeps_version():
    g = ground_question("杠杆坐姿划船 v. 2 练哪里")
    assert g.branch == "kb"
    assert g.citations == ["2265"]


def test_spaced_version_matches_catalog_version():
    g = ground_question("绳索直臂下拉v.2 练哪里")
    assert g.branch == "kb"
    assert g.citations == ["6036"]


def test_family_name_is_explained_without_a_menu():
    g = ground_question("坐姿划船练哪里")
    assert g.branch == "knowledge"
    assert g.reason == "family"
    assert g.hit is False
    assert g.citations == []
    assert g.suggestions == []
    assert "坐姿划船" in g.passage
    assert "变体" in g.passage
    assert "名字例如" not in g.passage


def test_family_comparison_is_not_a_menu():
    g = ground_question("那高位下拉和划船有啥区别")
    assert g.branch == "compare"
    assert g.reason == "family"
    assert g.hit is False
    assert g.citations == []
    assert g.direct_answer == ""
    assert "高位下拉" in g.passage
    assert "划船" in g.passage
    assert "变体" in g.passage
    assert "名字例如" not in g.passage


def test_single_family_is_not_a_menu():
    g = ground_question("高位下拉练哪里")
    assert g.branch == "knowledge"
    assert g.suggestions == []


def test_smith_seated_row_corrects_to_smith_rows():
    g = ground_question("史密斯坐姿划船练哪里")
    labels = [item["label"] for item in g.suggestions if item["label"] != "都不是"]
    assert g.branch == "ask"
    assert labels
    assert all("划船" in name for name in labels)
    assert all("提踵" not in name for name in labels)
    assert "没有「史密斯坐姿划船」这个叫法" in g.direct_answer
    assert "背" in g.direct_answer


def test_hammer_row_has_no_similar_name():
    g = ground_question("悍马划船练哪里")
    assert g.branch == "search"
    assert g.reason == "below_miss"
    assert g.suggestions == []
    assert "杠杆" not in (g.direct_answer or "")


def test_frequency_misses_catalog():
    g = ground_question("新手一周练几次背合适")
    assert g.branch == "search"
    assert g.reason == "below_miss"
    assert g.queried is True


def test_anatomy_label_is_not_an_exercise_hit():
    g = ground_question("股四头肌练哪里")
    assert g.branch == "search"
    assert g.reason == "anatomy"
    assert g.citations == []
    assert all(h["id"] != "3533" for h in g.hits + g.near_miss)


def test_reject_options_searches_original_wording():
    history = [
        {"role": "user", "text": "悍马划船怎么练"},
        {"role": "assistant", "text": "库里没有叫「悍马划船」的条目。"},
    ]
    g = ground_question("都不是", history)
    assert g.branch == "search"
    assert "悍马划船" in (g.search_query or "")
    assert "杠杆坐姿划船" not in (g.search_query or "")


def test_hyperextension_spine():
    g = ground_question("山羊挺身练哪里")
    assert g.citations == ["0489"]
    assert "竖脊肌" in g.direct_answer
