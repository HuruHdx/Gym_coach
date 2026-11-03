"""问答知识库：动作文档检索，以及 kb / ask / search 的分数判定。

精确名和三条杠铃约定走知识库。名称只是沾边就反问。对不上才搜索。
判定不交给模型。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

from app.exercises_catalog import looks_like_exercise_name
from app.taxonomy import normalize_exercise_name

# 只此三条。坐姿划船、高位下拉、腿举、双杠臂屈伸不在这里。
QA_CANONICAL: dict[str, str] = {
    "深蹲": "杠铃深蹲",
    "硬拉": "杠铃硬拉",
    "卧推": "杠铃卧推",
}

TARGET_ZH: dict[str, str] = {
    "lats": "背阔肌",
    "upper back": "上背",
    "traps": "斜方肌",
    "spine": "竖脊肌",
    "lower back": "下背",
    "pectorals": "胸大肌",
    "chest": "胸",
    "delts": "三角肌",
    "shoulders": "三角肌",
    "biceps": "肱二头肌",
    "triceps": "肱三头肌",
    "forearms": "前臂",
    "quads": "股四头肌",
    "hamstrings": "腘绳肌",
    "glutes": "臀",
    "abs": "腹直肌",
    "calves": "小腿",
    "abductors": "髋外展",
    "adductors": "髋内收",
    "serratus anterior": "前锯肌",
    "levator scapulae": "肩胛提肌",
    "cardiovascular system": "心肺",
}

_TAILS = (
    "练哪里",
    "练哪",
    "怎么做",
    "怎么练",
    "有什么区别",
    "有啥区别",
    "有什么不同",
    "有啥不同",
    "哪个好",
    "能不能做",
    "能做吗",
    "可以吗",
)
_NEEDLE_STOP = frozenset(
    {
        "新手",
        "一周",
        "几次",
        "合适",
        "怎么",
        "什么",
        "这个",
        "哪个",
        "今天",
        "不好",
        "可以",
        "我们",
        "自己",
        "训练",
        "动作",
        "区别",
        "不同",
    }
)
_REJECT = frozenset({"都不是", "不是这些", "都不是这些"})
# 动作词谁的动作都有，只对上这些不算相似。姿势词也不算用户说的那一块。
_MOVE_WORDS = (
    "划船",
    "卧推",
    "深蹲",
    "硬拉",
    "弯举",
    "下拉",
    "推举",
    "提踵",
    "飞鸟",
    "挺身",
    "引体",
    "臂屈伸",
    "平举",
)
_POSTURE_WORDS = (
    "坐姿",
    "站姿",
    "俯身",
    "仰卧",
    "俯卧",
    "跪姿",
    "单臂",
    "双臂",
    "窄距",
    "宽距",
    "反握",
    "正握",
    "交替",
)
_COMPARE_CUES = ("区别", "不同", "对比", "哪个好", "哪个更")
_COMPARE_TAILS = (
    "有什么区别",
    "有啥区别",
    "有什么不同",
    "有啥不同",
    "的区别",
    "的不同",
    "哪个更好",
    "哪个更适合",
    "哪个好",
    "哪个更",
    "更适合",
)
NO_SOURCE = "没有可靠来源。库内没有这条，外部也没有可用结果。"

_lock = threading.Lock()
_ready = False
_docs: list["Doc"] = []
_by_norm: dict[str, list["Doc"]] = {}
_by_en: dict[str, list["Doc"]] = {}
_substrings: set[str] = set()


@dataclass
class Doc:
    id: str
    name_zh: str
    name_en: str
    norm: str
    norm_en: str
    target_en: str
    target_zh: str
    passage: str

    def hit(self, score: float) -> dict[str, Any]:
        snippet = f"目标肌：{self.target_zh}（{self.target_en or 'unknown'}）"
        return {
            "id": self.id,
            "name": self.name_zh,
            "score": round(score, 4),
            "snippet": snippet,
            "target": self.target_zh,
        }


@dataclass
class Grounding:
    branch: str
    reason: str
    queried: bool
    hit: bool
    top_score: float = 0.0
    margin: float = 0.0
    hits: list[dict[str, Any]] = field(default_factory=list)
    near_miss: list[dict[str, Any]] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    suggestions: list[dict[str, str]] = field(default_factory=list)
    search_called: bool = False
    search_query: str | None = None
    search_results: list[dict[str, Any]] = field(default_factory=list)
    model_called: bool = False
    answer: str = ""
    direct_answer: str = ""
    passage: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "model_called": self.model_called,
            "suggestions": self.suggestions,
            "citations": self.citations,
            "answer": self.answer or self.direct_answer,
            "passage": self.passage,
            "kb": {
                "queried": self.queried,
                "hit": self.hit,
                "top_score": self.top_score,
                "margin": self.margin,
                "reason": self.reason,
                "hits": self.hits,
                "near_miss": self.near_miss,
            },
            "search": {
                "called": self.search_called,
                "query": self.search_query,
                "results": self.search_results,
            },
        }


def _target_zh(en: str) -> str:
    key = (en or "").strip().lower()
    return TARGET_ZH.get(key, "相关肌群")


def _muscle_pack(row: dict[str, Any], target_zh: str) -> tuple[str, str, str]:
    """目标肌 / 协同肌 / 参与（roles 补漏），合并去重后参与最多补到合计 4 项。"""
    from app.exercise_mapping import map_roles

    secondary = row.get("secondary_muscles") or []
    sec_list: list[str] = []
    if isinstance(secondary, list):
        for item in secondary:
            zh = _target_zh(str(item))
            if zh and zh not in sec_list and zh != target_zh and zh != "相关肌群":
                sec_list.append(zh)
    seen = {target_zh, *sec_list}
    roles: list[str] = []
    for role in map_roles(str(row.get("name_en") or ""), target_zh):
        name = str(role).strip()
        if name and name not in seen and name != "相关肌群":
            roles.append(name)
            seen.add(name)
        if len(seen) >= 4:
            break
    return target_zh, "、".join(sec_list), "、".join(roles)


def _passage(row: dict[str, Any], target_zh: str) -> str:
    steps = row.get("instructions_zh") or []
    if not isinstance(steps, list) or not steps:
        steps = row.get("instructions_en") or []
    step_text = " ".join(str(s) for s in steps[:6]) if isinstance(steps, list) else ""
    desc = row.get("description_zh") or row.get("description_en") or ""
    primary, sec, roles = _muscle_pack(row, target_zh)
    lines = [
        f"id: {row.get('id')}",
        f"名称：{row.get('name_zh')}",
        f"目标肌：{primary}（{row.get('target') or ''}）",
        f"协同肌：{sec or '（无）'}",
    ]
    if roles:
        lines.append(f"参与：{roles}")
    lines.append(f"步骤：{step_text}")
    lines.append(f"说明：{desc}")
    return "\n".join(lines)


def ensure_index() -> None:
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "assets" / "opengym" / "opengym_exercises_with_media.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        docs: list[Doc] = []
        by_norm: dict[str, list[Doc]] = {}
        by_en: dict[str, list[Doc]] = {}
        subs: set[str] = set()
        for row in raw:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name_zh") or "").strip()
            if not name:
                continue
            norm = normalize_exercise_name(name)
            en = str(row.get("name_en") or "").strip().lower()
            target_en = str(row.get("target") or "")
            tz = _target_zh(target_en)
            doc = Doc(
                id=str(row.get("id") or ""),
                name_zh=name,
                name_en=en,
                norm=norm,
                norm_en=normalize_exercise_name(en),
                target_en=target_en,
                target_zh=tz,
                passage=_passage(row, tz),
            )
            docs.append(doc)
            by_norm.setdefault(norm, []).append(doc)
            if doc.norm_en:
                by_en.setdefault(doc.norm_en, []).append(doc)
            upper = min(len(norm), 12)
            for length in range(2, upper + 1):
                for i in range(0, len(norm) - length + 1):
                    subs.add(norm[i : i + length])
        for bucket in by_norm.values():
            bucket.sort(key=lambda d: d.id)
        _docs[:] = docs
        _by_norm.clear()
        _by_norm.update(by_norm)
        _by_en.clear()
        _by_en.update(by_en)
        _substrings.clear()
        _substrings.update(subs)
        _ready = True


def _core(question: str) -> str:
    text = normalize_exercise_name(question)
    for tail in _TAILS:
        norm_tail = normalize_exercise_name(tail)
        if text.endswith(norm_tail) and len(text) > len(norm_tail):
            text = text[: -len(norm_tail)]
            break
    return text.strip("的呢啊呀吗 ")


def _cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _bare_canonical_keys(question: str) -> list[str]:
    """句子里单独出现的深蹲 / 硬拉 / 卧推。前面还粘着更长动作名时不算。"""
    found: list[str] = []
    for key in QA_CANONICAL:
        start = 0
        bare = False
        while True:
            index = question.find(key, start)
            if index < 0:
                break
            start = index + len(key)
            cursor = index
            while cursor > 0 and _cjk(question[cursor - 1]):
                cursor -= 1
            attached = question[cursor:index]
            if attached and any(norm.endswith(attached + key) for norm in _by_norm):
                continue
            bare = True
            break
        if bare:
            found.append(key)
    return found


def _contained_names(question_norm: str) -> list[str]:
    found = [norm for norm in _by_norm if norm and norm in question_norm]
    if not found:
        return []
    longest = max(len(n) for n in found)
    return [n for n in found if len(n) == longest]


def _english_names(question: str) -> list[str]:
    text = normalize_exercise_name(question.lower())
    found = [en for en in _by_en if en and en in text]
    if not found:
        return []
    longest = max(len(n) for n in found)
    return [n for n in found if len(n) == longest]


def _needle(core: str) -> str:
    best = ""
    n = len(core)
    for length in range(min(n, 12), 1, -1):
        for i in range(0, n - length + 1):
            piece = core[i : i + length]
            if piece in _NEEDLE_STOP or piece in QA_CANONICAL:
                continue
            if piece in _substrings and len(piece) > len(best):
                return piece
        if best:
            break
    return best


def _move_words(phrase: str) -> list[str]:
    return [word for word in _MOVE_WORDS if word in phrase]


def _distinctive_piece(core: str) -> str:
    """去掉动作词和姿势词，剩下的才是这个叫法本身。"""
    text = core
    for word in sorted(_MOVE_WORDS + _POSTURE_WORDS, key=len, reverse=True):
        text = text.replace(word, "")
    return text.strip()


def _catalog_token(piece: str) -> str:
    """剩下的那一块（或其中最长的一段）必须真的出现在正式名里。"""
    if len(piece) < 2:
        return ""
    if piece in _substrings:
        return piece
    for length in range(min(len(piece), 12), 1, -1):
        for i in range(0, len(piece) - length + 1):
            chunk = piece[i : i + length]
            if chunk in _substrings:
                return chunk
    return ""


def _similar_docs(core: str) -> list[Doc]:
    """正式名要同时对上动作词和剩下的那一块。只对上「划船」不算相似。"""
    moves = _move_words(core)
    token = _catalog_token(_distinctive_piece(core))
    if not moves or not token:
        return []
    return [
        doc
        for doc in _docs
        if looks_like_exercise_name(doc.name_zh)
        and token in doc.norm
        and any(word in doc.norm for word in moves)
    ]


def _pick(docs: list[Doc]) -> Doc:
    return sorted(docs, key=lambda d: d.id)[0]


def _margin(scores: list[float]) -> float:
    if len(scores) <= 1:
        return 1.0
    ordered = sorted(scores, reverse=True)
    return round(ordered[0] - ordered[1], 4)


def _choice_key(phrase: str, doc: Doc) -> tuple:
    name = doc.name_zh
    overlap = sum(1 for ch in phrase if ch in name)
    bonus = 0
    for token in ("史密斯", "罗马尼亚"):
        if token in phrase and token in name:
            bonus += 6
    # 已经对上同类正式名之后：没说直立、后三角时，俯身划更接近。
    if "划船" in phrase and "直立" not in phrase and "直立" in name:
        bonus -= 8
    if "划船" in phrase and "后三角" not in phrase and "后三角" in name:
        bonus -= 8
    if "划船" in phrase and "俯身" in name:
        bonus += 3
    return (-bonus, -overlap, len(name), doc.norm, doc.id)


def _ask(phrase: str, docs: list[Doc], *, missing_name: bool) -> Grounding:
    # 同一针的分数放在同一档，分差为 0，调低阈值也不能升成命中
    score = 0.72
    moves = _move_words(phrase)
    if moves:
        matched = [doc for doc in docs if any(word in doc.norm for word in moves)]
        if matched:
            docs = matched
    ranked = sorted({d.norm: d for d in docs}.values(), key=lambda d: _choice_key(phrase, d))
    chosen = ranked[:4]
    near = [_pick([d for d in docs if d.norm == item.norm]).hit(score) for item in chosen]
    labels = [item.name_zh for item in chosen]
    suggestions = [{"label": name, "prompt": f"{name}练哪里"} for name in labels]
    suggestions.append({"label": "都不是", "prompt": "都不是"})
    options = "、".join(labels)
    # 反问时顺带告诉用户这些候选练的部位，不让用户纯猜
    if any("划船" in name for name in labels):
        muscle_hint = "这类主要练背。"
    elif any("卧推" in name for name in labels):
        muscle_hint = "这类主要练胸。"
    elif any("深蹲" in name for name in labels):
        muscle_hint = "这类主要练腿。"
    else:
        muscle_hint = ""
    if missing_name:
        # 用户的叫法对不上正式名：纠正几个相近的，并先回答练哪里。
        answer = f"没有「{phrase}」这个叫法。按你说的动作，比较接近：{options}。{muscle_hint}要是都不是，我按你原来的问法去查。"
    else:
        answer = f"「{phrase}」有好几种，你指的是哪一个？{options}。{muscle_hint}都不是的话，我按你原来的问法去查。"
    return Grounding(
        branch="ask",
        reason="ambiguous",
        queried=True,
        hit=False,
        top_score=score,
        margin=0.0 if len(ranked) > 1 else 1.0,
        hits=near[:1],
        near_miss=near,
        suggestions=suggestions,
        answer=answer,
        direct_answer=answer,
    )


def _kb(docs: list[Doc], reason: str, spoken: str | None = None) -> Grounding:
    doc = _pick(docs)
    label = spoken or doc.name_zh
    answer = f"{label}主要练{doc.target_zh}。"
    hit = doc.hit(1.0)
    return Grounding(
        branch="kb",
        reason=reason,
        queried=True,
        hit=True,
        top_score=1.0,
        margin=1.0,
        hits=[hit],
        citations=[doc.id],
        direct_answer=answer,
        passage=doc.passage,
    )


def _search(reason: str, query: str) -> Grounding:
    return Grounding(
        branch="search",
        reason=reason,
        queried=True,
        hit=False,
        top_score=0.0,
        margin=0.0,
        search_query=query,
    )


def _clean_side(part: str) -> str:
    text = part.strip()
    for tail in _COMPARE_TAILS:
        if text.endswith(tail) and len(text) > len(tail):
            text = text[: -len(tail)]
            break
    return text.strip("那这个的吗呢啊呀？? ")


def _split_compare(question: str) -> list[str]:
    if not any(cue in question for cue in _COMPARE_CUES):
        return []
    for sep in ("还是", "跟", "与", "和"):
        if sep in question:
            left, right = question.split(sep, 1)
            return [left, right]
    return []


def _resolve_side(part: str) -> tuple[str, list[Doc]]:
    text = _clean_side(part)
    core = _core(text)
    label = core or text
    if not label:
        return label, []
    names = _contained_names(normalize_exercise_name(label))
    if len(names) == 1:
        name = names[0]
        if name in QA_CANONICAL:
            target = normalize_exercise_name(QA_CANONICAL[name])
            return name, list(_by_norm.get(target) or [])
        docs = [d for d in _by_norm[name] if looks_like_exercise_name(d.name_zh)]
        return name, docs
    keys = _bare_canonical_keys(label)
    if len(keys) == 1:
        target = normalize_exercise_name(QA_CANONICAL[keys[0]])
        return keys[0], list(_by_norm.get(target) or [])
    needle = _needle(label)
    if not needle:
        return label, []
    docs = [d for d in _docs if needle in d.norm and looks_like_exercise_name(d.name_zh)]
    return needle, docs


def _family(label: str) -> Grounding:
    passage = (
        f"学员在问一类动作「{label}」。\n"
        "按这个动作本身用口语讲清楚，可以展开发力、轨迹、握法和握距带来的侧重差别。\n"
        "不要列举动作库里的变体名称，不要让学员从名单里挑，不要提数据库，不要排成一堂训练。"
    )
    return Grounding(
        branch="knowledge",
        reason="family",
        queried=True,
        hit=False,
        passage=passage,
    )


def _compare(sides: list[tuple[str, list[Doc]]]) -> Grounding:
    left, right = sides[0][0], sides[1][0]
    passage = (
        f"学员在比较「{left}」和「{right}」这两类动作。\n"
        "用教练口语说明差别，可以讲动作方向、主要发力、各自适合什么时候练。\n"
        "不要列举动作库里的变体名称，不要让学员挑选，不要排成今天的训练计划。"
    )
    return Grounding(
        branch="compare",
        reason="family",
        queried=True,
        hit=False,
        passage=passage,
    )


def comparison_of(question: str) -> Grounding | None:
    """两段都对得上动作时，按类比较，不收成「选一个动作名」。"""
    ensure_index()
    parts = _split_compare(question)
    if len(parts) != 2:
        return None
    sides = [_resolve_side(part) for part in parts]
    if any(not docs for _, docs in sides):
        return None
    left = {d.norm for d in sides[0][1]}
    right = {d.norm for d in sides[1][1]}
    if not left or left == right:
        return None
    return _compare(sides)


def previous_user_question(history: list[Any] | None, current: str) -> str | None:
    if normalize_exercise_name(current) not in _REJECT and current.strip() not in _REJECT:
        return None
    for turn in reversed(history or []):
        role = turn.get("role") if isinstance(turn, dict) else getattr(turn, "role", "")
        if role not in ("user", "human"):
            continue
        text = turn.get("text") if isinstance(turn, dict) else getattr(turn, "text", "")
        text = str(text or "").strip()
        if text and normalize_exercise_name(text) not in _REJECT:
            return text
    return current


def ground_question(question: str, history: list[Any] | None = None) -> Grounding:
    """只做检索判定。搜索是否真正调用，由上层按 search_mode 填。"""
    ensure_index()
    rejected = previous_user_question(history, question)
    if rejected is not None and normalize_exercise_name(question) in _REJECT or question.strip() in _REJECT:
        decided = _search("below_miss", rejected)
        return decided

    compared = comparison_of(question)
    if compared is not None:
        return compared

    qnorm = normalize_exercise_name(question)
    core = _core(question)

    en_hits = _english_names(question)
    if len(en_hits) == 1:
        docs = _by_en[en_hits[0]]
        if looks_like_exercise_name(docs[0].name_zh):
            return _kb(docs, "exact_name")
    if len(en_hits) > 1:
        docs = [d for en in en_hits for d in _by_en[en]]
        return _ask(core or question, docs, missing_name=True)

    names = _contained_names(qnorm)
    if len(names) > 1:
        docs = [d for name in names for d in _by_norm[name] if looks_like_exercise_name(d.name_zh)]
        if docs:
            return _ask(core or question, docs, missing_name=False)
    if len(names) == 1:
        name = names[0]
        if name in QA_CANONICAL:
            target = normalize_exercise_name(QA_CANONICAL[name])
            return _kb(_by_norm[target], "canonical", spoken=name)
        docs = _by_norm[name]
        if not looks_like_exercise_name(docs[0].name_zh):
            return _search("anatomy", question)
        return _kb(docs, "exact_name")

    if core in QA_CANONICAL:
        target = normalize_exercise_name(QA_CANONICAL[core])
        return _kb(_by_norm[target], "canonical", spoken=core)

    folded = qnorm.replace("座", "坐")
    if folded != qnorm:
        folded_names = _contained_names(folded)
        if len(folded_names) == 1:
            docs = [d for d in _by_norm[folded_names[0]] if looks_like_exercise_name(d.name_zh)]
            if docs:
                return _kb(docs, "exact_name")

    keys = _bare_canonical_keys(question)
    if len(keys) == 1:
        target = normalize_exercise_name(QA_CANONICAL[keys[0]])
        docs = _by_norm.get(target) or []
        if docs:
            return _kb(docs, "canonical", spoken=keys[0])

    if core and not looks_like_exercise_name(core) and core in _by_norm:
        return _search("anatomy", question)

    needle = _needle(core) if core else ""
    if needle and needle == core:
        return _family(needle)
    similar = _similar_docs(core) if core else []
    if similar:
        return _ask(core or question, similar, missing_name=True)
    if needle:
        moves = _move_words(core)
        # 只剩动作词对得上，或最长片段把动作词切掉了：没有相似正式名，交给模型。
        if moves and (needle in moves or not any(word in needle for word in moves)):
            return _search("below_miss", question)
        docs = [d for d in _docs if needle in d.norm and looks_like_exercise_name(d.name_zh)]
        if docs:
            return _ask(core or question, docs, missing_name=True)
    return _search("below_miss", question)


def muscle_answer_for(question: str, grounding: Grounding) -> str | None:
    """问练哪里时直接用地段落里的目标肌，避免模型换成别的肌群。"""
    if grounding.branch != "kb" or not grounding.direct_answer:
        return None
    if any(k in question for k in ("练哪里", "练哪", "哪里", "哪块")):
        return grounding.direct_answer
    return None
