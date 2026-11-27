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
    "肘屈伸",
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

# 听混字符族（兜底，不是「错词→对词」）。同族可互换；只在整名等长、逐字对上、且库内唯一时才改。
# 库里没有的动作不会被改写成别的名；主路径仍是把 Whisper 转准。
_ASR_SOUND = (
    "剧距",
    "做坐",
    "滑划",
    "传船",
    "价架",
    "载窄",
    "元圆",
    "肘酒久",
    "伸深身",
    "铃零玲",
    "杠钢岗",
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


def _has_highlight(session: Session, exercise_id: str) -> bool:
    return bool(
        session.exec(
            select(ExerciseMedia).where(
                ExerciseMedia.exercise_id == exercise_id,
                ExerciseMedia.role == "highlight_video",
                ExerciseMedia.status == "published",
            )
        ).first()
    )


def _pack(
    ex: Exercise,
    score: int,
    reason: str,
    *,
    has_demo: bool,
    has_highlight: bool = False,
) -> dict[str, Any]:
    is_female = bool((ex.variant_of or "").strip())
    has_female = bool((ex.female_variant or "").strip()) and not is_female
    return {
        "id": ex.id,
        "name_zh": ex.name_zh,
        "muscle": ex.muscle,
        "gear": ex.gear,
        "has_demo": has_demo,
        "has_highlight": has_highlight,
        "score": int(score),
        "reason": reason,
        "is_female_variant": is_female,
        "has_female_variant": has_female,
        "female_variant": (ex.female_variant or None) if has_female else None,
        "variant_of": (ex.variant_of or None) if is_female else None,
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
        out.append(
            _pack(
                ex,
                item["score"],
                item["reason"],
                has_demo=_has_demo(session, ex.id),
                has_highlight=_has_highlight(session, ex.id),
            )
        )
    return out


def repair_spoken_name(session: Session, spoken: str) -> str | None:
    """库里没有这个原词时，按同音错字改成唯一的标准名。

    只对照等长的库名/别名，不要求先抠出正确核心词（整名听错时 contains(core) 会找空）。
    """
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
    rows = session.exec(
        select(Exercise).where(
            Exercise.is_valid_exercise.is_(True),  # type: ignore[arg-type]
            func.char_length(Exercise.name_zh) == len(norm),
        )
    ).all()
    # 候选串 → 展示用标准名（别名命中时回写 name_zh）
    display_for: dict[str, str] = {}
    for r in rows:
        n = (r.name_zh or "").strip()
        if n:
            display_for[normalize_spoken_name(n)] = n
    aliases = session.exec(
        select(ExerciseAlias).where(func.char_length(ExerciseAlias.alias) == len(norm))
    ).all()
    for al in aliases:
        alias = (al.alias or "").strip()
        if not alias:
            continue
        ex = session.get(Exercise, al.exercise_id)
        if not ex or not getattr(ex, "is_valid_exercise", True):
            continue
        standard = (ex.name_zh or "").strip() or alias
        display_for[normalize_spoken_name(alias)] = standard
    repaired = suggest_asr_repair(norm, list(display_for.keys()))
    if not repaired:
        return None
    return display_for.get(normalize_spoken_name(repaired), repaired)


def prefer_female_candidates(
    candidates: list[dict[str, Any]],
    *,
    prefer_female: bool,
) -> list[dict[str, Any]]:
    """女性专项计划：女版候选置前；仅有男版时标注建议派生。"""
    if not prefer_female or not candidates:
        return candidates
    female = [c for c in candidates if c.get("is_female_variant")]
    male_only = [c for c in candidates if c.get("has_female_variant")]
    other = [c for c in candidates if not c.get("is_female_variant") and not c.get("has_female_variant")]
    # 男版且尚无女版：提示派生，避免女计划直接绑男版盖示范
    for c in other:
        if not c.get("is_female_variant"):
            c["prefer_derive_female"] = True
            reason = str(c.get("reason") or "")
            if "建议派生女版" not in reason:
                c["reason"] = f"{reason}·建议派生女版" if reason else "建议派生女版"
    # 已有女版链的男版：女计划里压后，优先展示女版
    for c in male_only:
        c["prefer_derive_female"] = False
        c["score"] = max(0, int(c.get("score") or 0) - 8)
    ordered = female + other + male_only
    return ordered


def resolve_spoken_match(
    session: Session,
    spoken: str,
    *,
    muscle_hint: str | None = None,
    limit: int = 3,
    prefer_female: bool = False,
) -> dict[str, Any]:
    """主命中 + 候选列表。

    - score≥90 且非含糊：自动预填主命中
    - 55～89：只给候选，主命中为空（等人点选）
    - <55：新动作路径
    - prefer_female：女性专项计划，候选优先女版
    """
    # 多取一些再重排，避免女版被截在 limit 外
    fetch_n = max(limit, 6) if prefer_female else limit
    candidates = match_spoken_candidates(session, spoken, limit=fetch_n, muscle_hint=muscle_hint)
    candidates = prefer_female_candidates(candidates, prefer_female=prefer_female)[:limit]
    hit: dict[str, Any] | None = None
    if candidates:
        top = candidates[0]
        # 女计划不自动绑男版（即使分够），避免切片盖示范
        if prefer_female and top.get("prefer_derive_female") and not top.get("is_female_variant"):
            hit = None
        elif int(top["score"]) >= _AUTO_BIND_MIN and not is_ambiguous_spoken(spoken):
            hit = {
                "id": top["id"],
                "name_zh": top["name_zh"],
                "muscle": top["muscle"],
                "gear": top["gear"],
                "has_demo": top["has_demo"],
                "has_highlight": bool(top.get("has_highlight")),
                "confidence": top["score"] / 100.0,
                "score": top["score"],
                "reason": top["reason"],
                "is_female_variant": bool(top.get("is_female_variant")),
                "has_female_variant": bool(top.get("has_female_variant")),
            }
    return {
        "hit": hit,
        "candidates": candidates,
        "ambiguous": is_ambiguous_spoken(spoken),
        "match_score": int(candidates[0]["score"]) if candidates else 0,
    }
