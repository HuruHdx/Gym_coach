from __future__ import annotations

from typing import Any

from app.exercise_mapping import INJURY_NAME_KEYWORDS, injury_keywords_for
from app.exercises_catalog import EXERCISE_BY_NAME, ensure_loaded, is_banned_for_injuries, looks_like_exercise_name, roles_of
from app.schemas import CardBlock, CardItem, CardStatus, CardType, TextBlock
from app.taxonomy import Muscle, canonicalize_exercise

_ALLOWED_MUSCLES = {m.value for m in Muscle}
_NO_WEIGHT_MODALITIES = frozenset({"有氧", "HIIT", "灵活性"})


def _rebuild_subtitle(meta: dict[str, Any]) -> str:
    sets = meta.get("sets")
    reps = meta.get("reps") or "-"
    weight = meta.get("weight")
    parts: list[str] = []
    if sets is not None:
        parts.append(f"{sets}×{reps}")
    else:
        parts.append(str(reps))
    if weight is not None:
        parts.append(f"建议 {weight}kg")
    elif meta.get("bodyweight"):
        parts.append("自重")
    return " · ".join(parts) if parts else ""


def validate_and_build_blocks(
    raw: dict[str, Any],
    injuries: list[str],
    allow: list[str] | None = None,
) -> list[TextBlock | CardBlock]:
    blocks: list[TextBlock | CardBlock] = []
    text = str(raw.get("text") or "").strip() or "这是一版建议。"
    blocks.append(TextBlock(text=text))

    card = raw.get("card")
    if not isinstance(card, dict):
        return blocks

    items_in = card.get("items") or []
    items: list[CardItem] = []
    dropped: list[str] = []
    for i, it in enumerate(items_in):
        if not isinstance(it, dict):
            continue
        title = canonicalize_exercise(str(it.get("title") or f"动作{i+1}"))
        meta = dict(it.get("meta") or {})
        muscle = str(meta.get("muscle") or "")
        if is_banned_for_injuries(title, injuries) and not _injury_allowed(title, allow, injuries):
            dropped.append(title)
            continue
        detail = EXERCISE_BY_NAME.get(title)
        modality = (detail or {}).get("modality") or "抗阻"
        meta["modality"] = modality
        if detail and (detail.get("category") == "自重" or modality in _NO_WEIGHT_MODALITIES):
            meta.pop("weight", None)
            meta["bodyweight"] = True
            meta["no_load"] = modality in _NO_WEIGHT_MODALITIES
        chosen = str(meta.get("muscle") or muscle).strip()
        allowed_roles = roles_of(title, detail)
        if chosen in _ALLOWED_MUSCLES and (not allowed_roles or chosen in allowed_roles or not detail):
            meta["muscle"] = chosen
        elif detail:
            # 模型没选或选飞了：才退回目录默认展示位
            meta["muscle"] = detail["muscle"]
        elif chosen in _ALLOWED_MUSCLES:
            meta["muscle"] = chosen
        else:
            meta["muscle"] = muscle or "全身"
        if "sets" in meta:
            try:
                meta["sets"] = int(meta["sets"])
            except (TypeError, ValueError):
                meta["sets"] = 3
        if "weight" in meta and meta["weight"] is not None:
            try:
                meta["weight"] = float(meta["weight"])
            except (TypeError, ValueError):
                meta.pop("weight", None)
        # 卡片只展示组次和重量。做法留到动作库示例，不采用模型写进 subtitle 的要领。
        subtitle = _rebuild_subtitle(meta)
        items.append(
            CardItem(
                id=str(it.get("id") or f"i{i}"),
                title=title,
                subtitle=subtitle,
                meta=meta,
                selected=bool(it.get("selected", True)),
            )
        )

    try:
        card_type = CardType(card.get("card_type", "training_draft"))
    except ValueError:
        card_type = CardType.TRAINING_DRAFT

    note = ""
    if dropped:
        note = f"已按伤痛规避：{'、'.join(dropped)}"
        if text and note not in text:
            blocks[0] = TextBlock(text=f"{text}\n（{note}）")

    blocks.append(
        CardBlock(
            card_type=card_type,
            title=str(card.get("title") or "建议"),
            status=CardStatus.DRAFT,
            items=items,
            actions=["adopt", "customize"],
            meta={"dropped": dropped} if dropped else {},
        )
    )
    return blocks


def _draft_load(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        title = str(item.get("title") or "")
        meta = dict(item.get("meta") or {})
    else:
        title = str(getattr(item, "title", "") or "")
        meta = dict(getattr(item, "meta", None) or {})
    weight = meta.get("weight")
    if weight is None or weight == "":
        return None
    try:
        weight = float(weight)
    except (TypeError, ValueError):
        return None
    return {
        "title": canonicalize_exercise(title) or title,
        "weight": weight,
        "sets": meta.get("sets"),
        "reps": str(meta.get("reps") or ""),
        "used": False,
    }


def _title_score(meta: dict[str, Any], prev: dict[str, Any], title: str) -> int:
    if prev["title"] != title:
        return 0
    sets_match = str(prev["sets"]) == str(meta.get("sets"))
    reps_match = prev["reps"] == str(meta.get("reps") or "")
    if sets_match and reps_match:
        return 4
    if reps_match:
        return 3
    if sets_match:
        return 2
    return 1


def carry_forward_weights(
    blocks: list[TextBlock | CardBlock],
    draft_items: list[Any] | None,
) -> list[TextBlock | CardBlock]:
    """改上一张时，模型漏写的重量从上一张补回。换掉的动作把重量交给新换上的那项。"""
    prev = [row for item in (draft_items or []) if (row := _draft_load(item))]
    if not prev:
        return blocks
    out: list[TextBlock | CardBlock] = []
    for block in blocks:
        if getattr(block, "kind", None) != "card":
            out.append(block)
            continue
        items = list(block.items)
        pairs: list[tuple[int, int, int]] = []
        skip: set[int] = set()
        for idx, item in enumerate(items):
            meta = dict(item.meta or {})
            title = canonicalize_exercise(item.title) or item.title
            if meta.get("bodyweight") or meta.get("no_load") or meta.get("weight") is not None:
                skip.add(idx)
                for row in prev:
                    if not row["used"] and row["title"] == title:
                        row["used"] = True
                        break
                continue
            for pi, row in enumerate(prev):
                score = _title_score(meta, row, title)
                if score:
                    pairs.append((score, idx, pi))
        pairs.sort(key=lambda pair: pair[0], reverse=True)
        taken: set[int] = set()
        updated = list(items)
        matched = 0
        for _score, idx, pi in pairs:
            if idx in taken or prev[pi]["used"]:
                continue
            prev[pi]["used"] = True
            taken.add(idx)
            item = updated[idx]
            meta = dict(item.meta or {})
            meta["weight"] = prev[pi]["weight"]
            updated[idx] = item.model_copy(update={"meta": meta, "subtitle": _rebuild_subtitle(meta)})
            matched += 1
        if matched == 0:
            out.append(block)
            continue
        new_titles = {canonicalize_exercise(item.title) or item.title for item in updated}
        for idx, item in enumerate(updated):
            if idx in skip or idx in taken:
                continue
            meta = dict(item.meta or {})
            if meta.get("weight") is not None or meta.get("bodyweight") or meta.get("no_load"):
                continue
            donors = [
                row
                for row in prev
                if not row["used"]
                and row["title"] not in new_titles
                and str(row["sets"]) == str(meta.get("sets"))
                and row["reps"] == str(meta.get("reps") or "")
            ]
            if len(donors) != 1:
                continue
            donors[0]["used"] = True
            meta["weight"] = donors[0]["weight"]
            updated[idx] = item.model_copy(update={"meta": meta, "subtitle": _rebuild_subtitle(meta)})
        out.append(block.model_copy(update={"items": updated}))
    return out


def title_matches_dropped(title: str | None, dropped: list[str]) -> bool:
    if not title or not dropped:
        return False
    canon = canonicalize_exercise(title)
    return any(canon == name or title in name or name in canon for name in dropped)


def _requested_drops(raw: str, focus: list[str], dropped: list[str]) -> list[str]:
    """用户这句点到的、又被伤痛拿掉的动作。没点名的顺手规避不算。"""
    text = raw or ""
    hits: list[str] = []
    for name in dropped:
        if name in text:
            hits.append(name)
            continue
        spoken = False
        for piece in focus:
            token = str(piece or "")
            canon = canonicalize_exercise(token)
            if token and (token in name or canon == name or name in canon):
                spoken = True
                break
        if spoken:
            hits.append(name)
            continue
        span = min(len(text), 8)
        for length in range(span, 1, -1):
            found = False
            for i in range(0, len(text) - length + 1):
                piece = text[i : i + length]
                if canonicalize_exercise(piece) == name:
                    hits.append(name)
                    found = True
                    break
            if found:
                break
    return list(dict.fromkeys(hits))


_INSIST_CUES = ("就要", "还是要", "坚持", "照样", "必须")


def spoken_name(canonical: str, raw: str, focus: list[str]) -> str:
    for piece in focus:
        token = str(piece or "")
        if token and canonicalize_exercise(token) == canonical:
            return token
    text = raw or ""
    best = ""
    span = min(len(text), 8)
    for length in range(span, 1, -1):
        for i in range(0, len(text) - length + 1):
            piece = text[i : i + length]
            if canonicalize_exercise(piece) == canonical and len(piece) > len(best):
                best = piece
        if best:
            break
    return best or canonical


_REFUSAL = ("不要", "别", "去掉", "不做", "排除", "避开", "没有", "不排", "别排")
_NAME_LEADS = ("我想做", "我想练", "我要做", "我要练", "帮我做", "帮我练")
_GEAR_PREFIX = ("史密斯机", "弹力带", "EZ杠铃", "哑铃", "杠铃", "壶铃", "绳索", "杠杆")
_TRAIL_STOP = ("有点", "不舒服", "疼", "痛", "酸", "今天", "这个", "那个", "可以", "但是", "然后")


def _remember(found: list[str], name: str) -> None:
    if not name or any(name == old or name in old or old in name for old in found):
        return
    found[:] = [old for old in found if old not in name]
    found.append(name)


def _keyword_requested(text: str, keyword: str) -> bool:
    if not text or not keyword or len(keyword) < 2:
        return False
    lowered = text.lower()
    key = keyword.lower()
    start = 0
    while True:
        idx = lowered.find(key, start)
        if idx < 0:
            return False
        before = text[idx - 1] if idx else ""
        after = text[idx + len(keyword)] if idx + len(keyword) < len(text) else ""
        window = text[max(0, idx - 4) : idx]
        ascii_stuck = keyword.isascii() and (
            (before.isascii() and before.isalpha()) or (after.isascii() and after.isalpha())
        )
        if before != "不" and not ascii_stuck and not any(flag in window for flag in _REFUSAL):
            return True
        start = idx + len(keyword)


def _spoken_phrase(text: str, keyword: str) -> str:
    lowered = text.lower()
    idx = lowered.find(keyword.lower())
    if idx < 0:
        return keyword
    end = idx + len(keyword)
    while end < len(text) and "\u4e00" <= text[end] <= "\u9fff":
        if any(text.startswith(stop, end) for stop in _TRAIL_STOP):
            break
        end += 1
    start = idx
    head = text[:idx]
    for gear in _GEAR_PREFIX:
        if head.endswith(gear):
            start = idx - len(gear)
            break
    return text[start:end] or keyword


def _injury_allowed(title: str, allow: list[str] | None, injuries: list[str]) -> bool:
    names = [canonicalize_exercise(name) for name in (allow or []) if name]
    if title in names:
        return True
    if any(name and (name in title or title in name) for name in names):
        return True
    keys = [
        key
        for key in injury_keywords_for(injuries)
        if len(key) >= 2 and any(key.lower() in name.lower() for name in names)
    ]
    blob = title.lower()
    return any(key.lower() in blob for key in keys)


def _explicit_names(raw: str, focus: list[str]) -> list[str]:
    """用户点到的动作名。不要求这个名字已经在动作库里。"""
    names: list[str] = []
    for piece in focus:
        token = str(piece or "").strip()
        if looks_like_exercise_name(token):
            names.append(token)
    text = raw or ""
    for lead in _NAME_LEADS:
        start = 0
        while True:
            at = text.find(lead, start)
            if at < 0:
                break
            rest = text[at + len(lead) :]
            end = 0
            while end < len(rest) and "\u4e00" <= rest[end] <= "\u9fff":
                if any(rest.startswith(stop, end) for stop in _TRAIL_STOP):
                    break
                end += 1
            parts = [rest[:end]]
            for sep in "和与、及":
                parts = [bit for part in parts for bit in part.split(sep)]
            for part in parts:
                token = part.strip()
                if looks_like_exercise_name(token):
                    names.append(token)
            start = at + len(lead)
    return list(dict.fromkeys(names))


def _phrase_refused(text: str, phrase: str) -> bool:
    if not text or phrase not in text:
        return False
    return not _keyword_requested(text, phrase)


def _in_library(phrase: str) -> bool:
    canon = canonicalize_exercise(phrase)
    if canon in EXERCISE_BY_NAME:
        return True
    if len(phrase) < 2:
        return False
    return any(phrase in name for name in EXERCISE_BY_NAME)


def named_banned_exercises(raw: str, focus: list[str], injuries: list[str]) -> list[str]:
    """这句点到、且要先问的动作。没点名的不在这里。

    库里的伤痛动作要问。用户点了名、但动作库里没有的，也按同样优先级先问，不写死某一个名字。
    「不过头」「不要硬拉」这种否定不算。
    """
    if not injuries:
        return []
    ensure_loaded()
    found: list[str] = []
    pieces = [str(piece) for piece in focus if piece]
    text = raw or ""
    span = min(len(text), 8)
    for length in range(span, 1, -1):
        for i in range(0, len(text) - length + 1):
            piece = text[i : i + length]
            if any("\u4e00" <= ch <= "\u9fff" for ch in piece):
                pieces.append(piece)
    for piece in pieces:
        canon = canonicalize_exercise(piece)
        if not canon:
            continue
        if canon == piece and canon not in EXERCISE_BY_NAME:
            continue
        if is_banned_for_injuries(canon, injuries):
            _remember(found, canon)
    for keyword in injury_keywords_for(injuries):
        if not _keyword_requested(text, keyword) and not any(_keyword_requested(str(piece), keyword) for piece in focus):
            continue
        source = text if _keyword_requested(text, keyword) else next(
            (str(piece) for piece in focus if _keyword_requested(str(piece), keyword)),
            keyword,
        )
        phrase = _spoken_phrase(source, keyword)
        canon = canonicalize_exercise(phrase)
        name = canon if canon in EXERCISE_BY_NAME or canon != phrase else phrase
        if is_banned_for_injuries(name, injuries) or is_banned_for_injuries(phrase, injuries):
            _remember(found, name if is_banned_for_injuries(name, injuries) else phrase)
    for phrase in _explicit_names(text, focus):
        if _phrase_refused(text, phrase):
            continue
        canon = canonicalize_exercise(phrase)
        banned = is_banned_for_injuries(canon, injuries) or is_banned_for_injuries(phrase, injuries)
        if banned:
            _remember(found, canon if canon in EXERCISE_BY_NAME or canon != phrase else phrase)
        elif not _in_library(phrase):
            _remember(found, phrase)
    return found


def _mentions(text: str, name: str) -> bool:
    if not text or not name:
        return False
    if name in text:
        return True
    span = min(len(text), 8)
    for length in range(span, 1, -1):
        for i in range(0, len(text) - length + 1):
            if canonicalize_exercise(text[i : i + length]) == name:
                return True
    return False


def _assistant_texts(history: list[Any] | None) -> list[str]:
    texts: list[str] = []
    for turn in reversed(history or []):
        role = turn.get("role") if isinstance(turn, dict) else getattr(turn, "role", "")
        if role not in ("assistant", "ai"):
            continue
        text = turn.get("text") if isinstance(turn, dict) else getattr(turn, "text", "")
        if text:
            texts.append(str(text))
        if len(texts) >= 3:
            break
    return texts


def user_insists(raw: str, history: list[Any] | None, names: list[str]) -> bool:
    """明确说就要，或上一轮已拒绝后再次点同一个动作。"""
    if not names:
        return False
    text = raw or ""
    if any(cue in text for cue in _INSIST_CUES) and any(_mentions(text, name) for name in names):
        return True
    for prev in _assistant_texts(history):
        if "这版不加" not in prev and "仍按" not in prev:
            continue
        if any(_mentions(prev, name) and _mentions(text, name) for name in names):
            return True
    return False


def _injury_spoken(injuries: list[str]) -> str:
    parts: list[str] = []
    for item in injuries or []:
        name = str(item).strip()
        if not name:
            continue
        parts.append(name if "伤" in name else f"{name}有伤")
    return "、".join(parts) or "有伤处"


def _safer_offer(injuries: list[str]) -> tuple[str, str]:
    """按钮文案，以及问句里要换成的具体做法。"""
    joined = "".join(injuries or [])
    if any(key in joined for key in ("腰", "背", "脊椎")):
        return "换成臀桥", "臀桥这类更轻的后链"
    if any(key in joined for key in ("膝", "髌", "半月板")):
        return "换成少冲击的", "少冲击、少屈膝的动作"
    if "肩" in joined:
        return "换成不过头的", "不过头的推举"
    if any(key in joined for key in ("腕", "肘")):
        return "换成更轻的", "对腕肘负担更小的动作"
    return "换成更轻的同类", "对伤处更轻的同类动作"


def _safer_direction(injuries: list[str]) -> str:
    _label, offer = _safer_offer(injuries)
    return f"可以换成{offer}。"


def _sites_for_named(injuries: list[str], names: list[str]) -> list[str]:
    """问句只提和这个动作有关的伤，不把画像里其他部位串进来。"""
    blob = "".join(names).lower()
    sites: list[str] = []
    for item in injuries or []:
        clean = str(item).strip()
        if not clean:
            continue
        words: list[str] = []
        for key, keywords in INJURY_NAME_KEYWORDS.items():
            if key in clean:
                words.extend(keywords)
        if any(len(word) >= 2 and word.lower() in blob for word in words):
            sites.append(clean)
    return sites


def injury_confirm(
    injuries: list[str],
    names: list[str],
    raw: str,
    focus: list[str],
    draft_title: str | None = None,
) -> dict[str, Any]:
    """第一次点名伤痛动作：只问一句，不出卡片。"""
    matched = _sites_for_named(injuries, names)
    sites = matched or [str(item).strip() for item in injuries or [] if str(item).strip()]
    shown = "、".join(spoken_name(name, raw, focus) for name in names)
    session = draft_title or "今天的课"
    if matched or len(sites) <= 1:
        label, offer = _safer_offer(sites)
    else:
        label, offer = "换成更轻的同类", "对伤处更轻的同类动作"
    safer_prompt = f"继续排{session}，避开伤痛动作。可以换成{offer}。"
    insist_prompt = f"还是要{shown}"
    return {
        "text": f"{_injury_spoken(sites)}，{shown}负担比较大。要换成{offer}，还是仍按{shown}排？",
        "suggestions": [
            {"label": label, "prompt": safer_prompt},
            {"label": insist_prompt[:20], "prompt": insist_prompt},
        ],
    }


_RAISE_CUES = (
    "加点",
    "加强度",
    "强度太低",
    "强度低",
    "太轻",
    "再重点",
    "加重",
    "提高强度",
    "强度上来",
    "强度不够",
    "不够强",
)
_RAISE_BLOCK = ("不要加重", "别加重", "不加强度", "不要加强")


def is_intensity_raise(raw: str) -> bool:
    text = raw or ""
    if any(cue in text for cue in _RAISE_BLOCK):
        return False
    return any(cue in text for cue in _RAISE_CUES)


def user_demands_heavier(raw: str, history: list[Any] | None) -> bool:
    """说过不建议之后，用户还是要求加重。"""
    text = raw or ""
    direct = ("还是要加重", "还是要大重量", "坚持加重", "就要大重量", "按大重量", "仍要加重", "还是按大重量")
    if any(phrase in text for phrase in direct):
        return True
    if any(cue in text for cue in _INSIST_CUES) and any(key in text for key in ("重", "强度", "力竭")):
        return True
    warned = any("不建议" in prev and "如果你还是要求" in prev for prev in _assistant_texts(history))
    if warned and (is_intensity_raise(text) or any(cue in text for cue in _INSIST_CUES)):
        return True
    return False


def intensity_advice(injuries: list[str]) -> dict[str, Any]:
    """有伤还要加强度：先说不建议，不改卡片。"""
    where = _injury_spoken(injuries)
    return {
        "text": (
            f"{where}，不建议把重量加大或做到接近力竭。"
            "如果你还是要求加重，那就按大重量、低次数改，不适就停。"
        ),
        "suggestions": [{"label": "还是要加重", "prompt": "还是要加重"}],
    }


def apply_heavy_demand_text(
    blocks: list[TextBlock | CardBlock],
    injuries: list[str],
) -> list[TextBlock | CardBlock]:
    spot = "、".join(injuries) if injuries else "伤处"
    text = f"按你的要求加重了。练的时候{spot}不舒服就停。"
    return _replace_text_and_title(blocks, text, None)


def injury_advice_suggestions(names: list[str], raw: str, focus: list[str]) -> list[dict[str, str]]:
    tips: list[dict[str, str]] = []
    for name in names:
        spoken = spoken_name(name, raw, focus)
        label = f"还是要{spoken}"
        tips.append({"label": label[:20], "prompt": label})
    return tips


def _replace_text_and_title(
    blocks: list[TextBlock | CardBlock],
    text: str,
    title: str | None,
) -> list[TextBlock | CardBlock]:
    out: list[TextBlock | CardBlock] = []
    for block in blocks:
        if getattr(block, "kind", None) == "text":
            out.append(block.model_copy(update={"text": text}))
        elif getattr(block, "kind", None) == "card" and title:
            out.append(block.model_copy(update={"title": title}))
        else:
            out.append(block)
    return out


def reconcile_requested_injury_drop(
    blocks: list[TextBlock | CardBlock],
    *,
    raw: str,
    focus: list[str],
    injuries: list[str],
    previous_title: str | None,
    names: list[str] | None = None,
) -> list[TextBlock | CardBlock]:
    """第一次点名伤痛动作：拿掉，说明原因并给方向，标题不用这个动作。"""
    asked = list(names or [])
    if not asked:
        card = next((block for block in blocks if getattr(block, "kind", None) == "card"), None)
        dropped = [str(name) for name in ((getattr(card, "meta", None) or {}).get("dropped") or [])] if card else []
        asked = _requested_drops(raw, focus, dropped)
    if not asked:
        return blocks
    where = "、".join(injuries) if injuries else "伤痛"
    shown = "、".join(spoken_name(name, raw, focus) for name in asked)
    text = f"{where}伤做{shown}负担大，这版不加。{_safer_direction(injuries)}"
    title = previous_title if previous_title and not title_matches_dropped(previous_title, asked) else None
    if title is None:
        card = next((block for block in blocks if getattr(block, "kind", None) == "card"), None)
        current = str(getattr(card, "title", "") or "")
        title = "训练" if title_matches_dropped(current, asked) else current or "训练"
    return _replace_text_and_title(blocks, text, title)


def apply_injury_insist(
    blocks: list[TextBlock | CardBlock],
    *,
    names: list[str],
    injuries: list[str],
    raw: str,
    focus: list[str],
    muscle: str,
) -> list[TextBlock | CardBlock]:
    """用户坚持：动作留在卡片里，只提醒不适就停。"""
    if not names:
        return blocks
    shown = "、".join(spoken_name(name, raw, focus) for name in names)
    where = "、".join(injuries) if injuries else "伤处"
    text = f"按你的要求排了{shown}。练的时候{where}不舒服就停。"
    card = next((block for block in blocks if getattr(block, "kind", None) == "card"), None)
    if card is None:
        return _replace_text_and_title(blocks, text, None)
    have = {item.title for item in card.items}
    items = list(card.items)
    for index, name in enumerate(names):
        if name in have:
            continue
        meta = {"sets": 3, "reps": "6-8", "muscle": muscle or "全身"}
        items.append(
            CardItem(
                id=f"insist{index}",
                title=name,
                subtitle=_rebuild_subtitle(meta),
                meta=meta,
                selected=True,
            )
        )
    titled = spoken_name(names[0], raw, focus) if len(names) == 1 else card.title
    out: list[TextBlock | CardBlock] = []
    for block in blocks:
        if getattr(block, "kind", None) == "text":
            out.append(block.model_copy(update={"text": text}))
        elif getattr(block, "kind", None) == "card":
            out.append(block.model_copy(update={"title": titled, "items": items}))
        else:
            out.append(block)
    return out
