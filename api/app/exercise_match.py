"""口播动作名 → 库内候选（百分制）。

产品口径：
- 大类（自由重量/器械/绳索/自重）只管 SKU 归类，不参与「像不像」主打分。
- 小词（杠铃/哑铃/上斜/罗马尼亚…）从名字里抠，用来区分候选。
- 含糊名（只说深蹲/卧推/硬拉）只枚举、不自作主张绑死。
- 打分统一 0～100；≥90 可预填，55～89 只出候选等人点，<55 当新动作。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models import Exercise, ExerciseAlias, ExerciseMedia
from app.taxonomy import EXERCISE_CANONICAL, normalize_exercise_name

# —— 匹配用小词（跨部位，不是 SKU 大类）——
_IMPLEMENTS = (
    "杠铃",
    "哑铃",
    "绳索",
    "龙门架",
    "史密斯",
    "固定器械",
    "器械",
    "弹力带",
    "拉力器",
    "自重",
    "壶铃",
    "TRX",
    "药球",
    "泡沫轴",
)
_IMPLEMENT_EN = {
    "barbell": "杠铃",
    "dumbbell": "哑铃",
    "cable": "绳索",
    "machine": "器械",
    "smith": "史密斯",
    "bodyweight": "自重",
    "resistanceband": "弹力带",
    "kettlebell": "壶铃",
}
_VARIANTS = (
    "上斜",
    "下斜",
    "平板",
    "平卧",
    "窄握",
    "窄距",
    "宽握",
    "单臂",
    "单腿",
    "反向",
    "俯身",
    "坐姿",
    "站姿",
    "跪姿",
    "罗马尼亚",
    "直腿",
    "相扑",
    "保加利亚",
    "哈克",
    "蝴蝶",
    "飞鸟",
)
# 核心动作词：越长越优先匹配
_CORES = (
    "罗马尼亚硬拉",
    "直腿硬拉",
    "硬拉",
    "卧推",
    "深蹲",
    "箭步蹲",
    "保加利亚蹲",
    "哈克深蹲",
    "高位下拉",
    "坐姿划船",
    "划船",
    "下拉",
    "推举",
    "肩推",
    "侧平举",
    "前平举",
    "弯举",
    "臂屈伸",
    "夹胸",
    "飞鸟",
    "腿举",
    "腿弯举",
    "腿伸展",
    "提踵",
    "引体向上",
    "双杠臂屈伸",
    "卷腹",
    "平板支撑",
    "早安",
    "臀桥",
    "髋推",
    "面拉",
)
_FILLERS = ("标准", "正确", "健身", "训练", "动作", "教程", "教学", "示范", "跟练")
# 单独说出这些词时视为含糊：必须枚举，禁止自动绑
_AMBIGUOUS_BARE = frozenset({"深蹲", "硬拉", "卧推", "划船", "下拉", "推举", "弯举", "夹胸", "飞鸟"})

_SCORE_EXACT = 100
_SCORE_ALIAS = 90
_SCORE_CORE_IMPL_VAR = 80
_SCORE_CORE_IMPL = 70
_SCORE_CORE_VAR = 65
_SCORE_CORE = 55
_SCORE_CONTAINS = 40
_AUTO_BIND_MIN = 90
_SUGGEST_MIN = 55

# 字幕错字：同音，以及平翘舌（z/zh）听混。只在整名等长、逐字能对上、且库里唯一时才改。
_ASR_SOUND = (
    "剧距",
    "做坐",
    "滑划",
    "传船",
    "价架",
    "载窄",
    "元圆",
)


def _asr_same(a: str, b: str) -> bool:
    if a == b:
        return True
    return any(a in group and b in group for group in _ASR_SOUND)


def suggest_asr_repair(spoken: str, catalog_names: list[str]) -> str | None:
    """口播整名对不上库时，用同音/平翘舌找唯一标准名。对不上或有多个就不改。"""
    norm = normalize_spoken_name(spoken)
    if len(norm) < 2:
        return None
    catalog = []
    for name in catalog_names:
        n = normalize_spoken_name(name or "")
        if n:
            catalog.append(n)
    if norm in catalog:
        return None
    hits: list[str] = []
    for name in dict.fromkeys(catalog):
        if len(name) != len(norm):
            continue
        if all(_asr_same(x, y) for x, y in zip(norm, name)):
            hits.append(name)
    if len(hits) == 1:
        return hits[0]
    return None


def normalize_spoken_name(name: str) -> str:
    """去空格/括号/无意义修饰，不做「深蹲→杠铃深蹲」硬改写。"""
    s = normalize_exercise_name(name or "")
    for w in _FILLERS:
        s = s.replace(w, "")
    # 英文器械 → 中文小词
    low = s.lower().replace(" ", "").replace("-", "").replace("_", "")
    for en, zh in _IMPLEMENT_EN.items():
        if en in low:
            s = re.sub(re.escape(en), zh, s, flags=re.I)
            low = s.lower().replace(" ", "")
    s = s.replace("平卧", "平板")
    return s


def decompose_spoken_name(spoken: str) -> dict[str, str]:
    raw = (spoken or "").strip()
    norm = normalize_spoken_name(raw)
    impl = ""
    for w in sorted(_IMPLEMENTS, key=len, reverse=True):
        if w in norm:
            impl = w
            break
    variants: list[str] = []
    rest = norm
    for w in sorted(_VARIANTS, key=len, reverse=True):
        if w in rest:
            variants.append(w)
            rest = rest.replace(w, "", 1)
    if impl:
        rest = rest.replace(impl, "", 1)
    core = ""
    for w in sorted(_CORES, key=len, reverse=True):
        if w in norm:
            core = w
            break
    if not core:
        core = rest or norm
    return {
        "raw": raw,
        "norm": norm,
        "core": core,
        "implement": impl,
        "variant": "".join(variants),
    }


def is_ambiguous_spoken(spoken: str) -> bool:
    parts = decompose_spoken_name(spoken)
    if parts["implement"] or parts["variant"]:
        return False
    return parts["norm"] in _AMBIGUOUS_BARE or parts["core"] in _AMBIGUOUS_BARE


def _has_demo(session: Session, exercise_id: str) -> bool:
    return bool(
        session.exec(
            select(ExerciseMedia).where(
                ExerciseMedia.exercise_id == exercise_id,
                ExerciseMedia.role == "demo",
                ExerciseMedia.status == "published",
            )
        ).first()
    )


def _pack(ex: Exercise, score: int, reason: str, *, has_demo: bool) -> dict[str, Any]:
    return {
        "id": ex.id,
        "name_zh": ex.name_zh,
        "muscle": ex.muscle,
        "gear": ex.gear,
        "has_demo": has_demo,
        "score": int(score),
        "reason": reason,
    }


def _soft_canonical_hint(norm: str) -> str | None:
    """同义词表只作加分线索，不把口语硬改成唯一 SKU 名。"""
    return EXERCISE_CANONICAL.get(norm)


def match_spoken_candidates(
    session: Session,
    spoken: str,
    *,
    limit: int = 3,
    muscle_hint: str | None = None,
) -> list[dict[str, Any]]:
    """返回 top N 候选，每项带 score(0-100) + reason。"""
    parts = decompose_spoken_name(spoken)
    norm = parts["norm"]
    if not norm:
        return []

    scored: dict[str, dict[str, Any]] = {}

    def bump(ex: Exercise | None, score: int, reason: str) -> None:
        if not ex or not getattr(ex, "is_valid_exercise", True):
            return
        # 部位不一致：降权，不排除
        if muscle_hint and ex.muscle and ex.muscle != muscle_hint and muscle_hint != "全身":
            if ex.muscle not in (muscle_hint,):
                score = max(0, score - 15)
                reason = f"{reason}·部位弱"
        cur = scored.get(ex.id)
        if cur and cur["score"] >= score:
            return
        scored[ex.id] = {
            "ex": ex,
            "score": score,
            "reason": reason,
        }

    # 1) 精确同名
    exact = session.exec(select(Exercise).where(Exercise.name_zh == norm)).all()
    for ex in exact:
        bump(ex, _SCORE_EXACT, "同名")

    # 2) 别名精确
    aliases = session.exec(select(ExerciseAlias).where(ExerciseAlias.alias == norm)).all()
    for al in aliases:
        ex = session.get(Exercise, al.exercise_id)
        bump(ex, _SCORE_ALIAS, "别名")

    # 3) 同义词表暗示的规范名（加分，不当唯一绑定）
    hint = _soft_canonical_hint(norm)
    if hint and hint != norm:
        for ex in session.exec(select(Exercise).where(Exercise.name_zh == hint)).all():
            # 含糊词走同义词时最多给到「核心」档，避免自动绑
            if is_ambiguous_spoken(spoken):
                bump(ex, _SCORE_CORE, "同义·含糊")
            else:
                bump(ex, _SCORE_ALIAS, "同义")

    # 4) 核心词 / 小词检索
    core = parts["core"]
    impl = parts["implement"]
    variant = parts["variant"]
    search_keys = [k for k in (core, norm[:4] if len(norm) >= 2 else norm) if k]
    pool: dict[str, Exercise] = {}
    for key in search_keys:
        if not key:
            continue
        rows = session.exec(
            select(Exercise)
            .where(
                Exercise.is_valid_exercise.is_(True),  # type: ignore[arg-type]
                col(Exercise.name_zh).contains(key),  # type: ignore[arg-type]
            )
            .limit(40)
        ).all()
        for ex in rows:
            pool[ex.id] = ex
        als = session.exec(
            select(ExerciseAlias)
            .where(col(ExerciseAlias.alias).contains(key))  # type: ignore[arg-type]
            .limit(20)
        ).all()
        for al in als:
            ex = session.get(Exercise, al.exercise_id)
            if ex:
                pool[ex.id] = ex

    for ex in pool.values():
        name = ex.name_zh or ""
        name_n = normalize_spoken_name(name)
        if name_n == norm:
            bump(ex, _SCORE_EXACT, "同名")
            continue
        has_core = bool(core) and core in name_n
        has_impl = bool(impl) and impl in name_n
        has_var = bool(variant) and any(v and v in name_n for v in (variant, "平板" if "平卧" in variant else ""))
        # 变体词逐个看
        if not has_var and variant:
            for v in _VARIANTS:
                if v in variant and v in name_n:
                    has_var = True
                    break
        if has_core and has_impl and has_var:
            bump(ex, _SCORE_CORE_IMPL_VAR, "核心+器械词+变式")
        elif has_core and has_impl:
            bump(ex, _SCORE_CORE_IMPL, "核心+器械词")
        elif has_core and has_var:
            bump(ex, _SCORE_CORE_VAR, "核心+变式")
        elif has_core:
            bump(ex, _SCORE_CORE, "核心")
        elif norm and (norm in name_n or name_n in norm):
            bump(ex, _SCORE_CONTAINS, "包含")
        elif len(norm) >= 2 and norm[:2] in name_n:
            bump(ex, _SCORE_CONTAINS, "包含")

    # 含糊名：封顶，禁止摸到自动绑阈值
    if is_ambiguous_spoken(spoken):
        for item in scored.values():
            if item["score"] >= _AUTO_BIND_MIN:
                item["score"] = _SCORE_CORE
                item["reason"] = f"{item['reason']}·含糊封顶"

    ranked = sorted(scored.values(), key=lambda x: (-x["score"], x["ex"].name_zh or ""))
    out: list[dict[str, Any]] = []
    for item in ranked[:limit]:
        ex = item["ex"]
        out.append(_pack(ex, item["score"], item["reason"], has_demo=_has_demo(session, ex.id)))
    return out


def repair_spoken_name(session: Session, spoken: str) -> str | None:
    """库里没有这个原词时，按同音错字改成唯一的标准名。"""
    norm = normalize_spoken_name(spoken)
    if len(norm) < 2:
        return None
    exact = session.exec(
        select(Exercise).where(
            Exercise.name_zh == norm,  # type: ignore[arg-type]
            Exercise.is_valid_exercise.is_(True),  # type: ignore[arg-type]
        )
    ).first()
    if exact:
        return None
    parts = decompose_spoken_name(norm)
    core = parts.get("core") or ""
    if len(core) < 2:
        return None
    rows = session.exec(
        select(Exercise).where(
            Exercise.is_valid_exercise.is_(True),  # type: ignore[arg-type]
            col(Exercise.name_zh).contains(core),  # type: ignore[arg-type]
            func.char_length(Exercise.name_zh) == len(norm),
        )
    ).all()
    return suggest_asr_repair(norm, [r.name_zh or "" for r in rows])


def resolve_spoken_match(
    session: Session,
    spoken: str,
    *,
    muscle_hint: str | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    """主命中 + 候选列表。

    - score≥90 且非含糊：自动预填主命中
    - 55～89：只给候选，主命中为空（等人点选）
    - <55：新动作路径
    """
    candidates = match_spoken_candidates(session, spoken, limit=limit, muscle_hint=muscle_hint)
    hit: dict[str, Any] | None = None
    if candidates:
        top = candidates[0]
        if int(top["score"]) >= _AUTO_BIND_MIN and not is_ambiguous_spoken(spoken):
            hit = {
                "id": top["id"],
                "name_zh": top["name_zh"],
                "muscle": top["muscle"],
                "gear": top["gear"],
                "has_demo": top["has_demo"],
                "confidence": top["score"] / 100.0,
                "score": top["score"],
                "reason": top["reason"],
            }
    return {
        "hit": hit,
        "candidates": candidates,
        "ambiguous": is_ambiguous_spoken(spoken),
        "match_score": int(candidates[0]["score"]) if candidates else 0,
    }
