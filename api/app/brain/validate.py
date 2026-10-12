from __future__ import annotations

from typing import Any

from app.exercises_catalog import EXERCISE_BY_NAME, is_banned_for_injuries, roles_of
from app.schemas import CardBlock, CardItem, CardStatus, CardType, TextBlock
from app.taxonomy import Muscle, canonicalize_exercise

_ALLOWED_MUSCLES = {m.value for m in Muscle}


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


def validate_and_build_blocks(raw: dict[str, Any], injuries: list[str]) -> list[TextBlock | CardBlock]:
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
        if is_banned_for_injuries(title, injuries):
            dropped.append(title)
            continue
        detail = EXERCISE_BY_NAME.get(title)
        if detail and detail.get("category") == "自重":
            meta.pop("weight", None)
            meta["bodyweight"] = True
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
        subtitle = it.get("subtitle") or _rebuild_subtitle(meta)
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
