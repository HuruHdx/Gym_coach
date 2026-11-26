"""把 pending 差评导出成 eval/inbox YAML 草稿（不进正式绿集）。

用法（在 api/ 下）:
  uv run python scripts/export_feedback_inbox.py
  uv run python scripts/export_feedback_inbox.py --out ../eval/inbox
  uv run python scripts/export_feedback_inbox.py --format auto
  uv run python scripts/export_feedback_inbox.py --format thread
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Literal

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import engine, init_db  # noqa: E402
from app.models import ChatTurn, FeedbackEvent  # noqa: E402

FormatMode = Literal["auto", "single", "thread"]


def _slug(text: str, limit: int = 24) -> str:
    cleaned = re.sub(r"\s+", "", (text or "").strip())
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "", cleaned)
    return (cleaned or "feedback")[:limit]


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if re.search(r'[:#\[\]{},&*!|>\'"%@`]', text) or text.strip() != text or "\n" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def _dump_yaml(data: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            return "{}"
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                if not value:
                    lines.append(f"{pad}{key}: {_dump_yaml(value, 0)}")
                else:
                    lines.append(f"{pad}{key}:")
                    lines.append(_dump_yaml(value, indent + 1))
            else:
                lines.append(f"{pad}{key}: {_yaml_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return "[]"
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                nested = _dump_yaml(item, indent + 1)
                first, *rest = nested.splitlines()
                lines.append(f"{pad}- {first.lstrip()}")
                for line in rest:
                    lines.append(line)
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{pad}{_yaml_scalar(data)}"


def _profile_block(snap: dict[str, Any]) -> dict[str, Any] | None:
    profile = snap.get("profile")
    if isinstance(profile, dict) and profile:
        return profile
    return None


def _observed(row: FeedbackEvent, snap: dict[str, Any]) -> dict[str, Any]:
    intent = snap.get("intent") if isinstance(snap.get("intent"), dict) else {}
    return {
        "topic": intent.get("topic"),
        "domain": intent.get("domain"),
        "route": snap.get("route"),
        "branch": snap.get("branch"),
        "answer": row.answer or snap.get("answer") or "",
    }


def _user_turns_from_snapshot(row: FeedbackEvent, snap: dict[str, Any]) -> list[str]:
    """把 history + 当前问句收成用户轮次字符串（对齐 cases-long vars.thread.turns）。"""
    turns: list[str] = []
    history = snap.get("history")
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and item.get("role") == "user":
                text = str(item.get("text") or "").strip()
                if text:
                    turns.append(text)
            elif isinstance(item, str) and item.strip():
                turns.append(item.strip())
    question = (row.question or snap.get("question") or "").strip()
    if question and (not turns or turns[-1] != question):
        turns.append(question)
    return turns


def _count_user_turns(
    session: Session | None,
    row: FeedbackEvent,
    snap: dict[str, Any],
) -> int:
    cid = (row.conversation_id or "").strip()
    if session is not None and cid:
        rows = list(
            session.exec(
                select(ChatTurn)
                .where(ChatTurn.conversation_id == cid)
                .where(ChatTurn.role == "user")
                .order_by(ChatTurn.id)
            ).all()
        )
        if rows:
            return len(rows)
    return len(_user_turns_from_snapshot(row, snap))


def _resolve_format(
    session: Session | None,
    row: FeedbackEvent,
    snap: dict[str, Any],
    mode: FormatMode,
) -> Literal["single", "thread"]:
    if mode == "single":
        return "single"
    if mode == "thread":
        return "thread"
    # auto：同一 conversation ≥ 2 轮用户对话 → 多轮；否则单轮
    return "thread" if _count_user_turns(session, row, snap) >= 2 else "single"


def _case_doc_single(row: FeedbackEvent, snap: dict[str, Any]) -> dict[str, Any]:
    tags = list(row.tags or [])
    tag_label = "+".join(tags) if tags else "other"
    vars_block: dict[str, Any] = {"question": row.question or snap.get("question") or ""}
    history = snap.get("history")
    if isinstance(history, list) and history:
        vars_block["history"] = history
    if snap.get("draft_title"):
        vars_block["draft_title"] = snap["draft_title"]
    if snap.get("draft_items"):
        vars_block["draft_items"] = snap["draft_items"]
    profile = _profile_block(snap)
    if profile:
        vars_block["profile"] = profile

    return {
        "description": f"FB-{row.id} 用户差评：{tag_label}",
        "tags": ["inbox", "from_feedback", *tags],
        "vars": vars_block,
        "meta": {
            "feedback_id": row.id,
            "tags": tags,
            "note": row.note or "",
            "format": "single",
            "observed": _observed(row, snap),
        },
        "assert": [
            {
                "type": "javascript",
                "value": "file://assertions/shape.js",
            },
        ],
    }


def _case_doc_thread(
    session: Session | None,
    row: FeedbackEvent,
    snap: dict[str, Any],
) -> dict[str, Any]:
    tags = list(row.tags or [])
    tag_label = "+".join(tags) if tags else "other"
    turns = _user_turns_from_snapshot(row, snap)
    cid = (row.conversation_id or "").strip()
    if session is not None and cid and len(turns) < 2:
        # 快照 history 不足时，尽量从 ChatTurn 补全用户轮次
        db_turns = [
            (t.text or "").strip()
            for t in session.exec(
                select(ChatTurn)
                .where(ChatTurn.conversation_id == cid)
                .where(ChatTurn.role == "user")
                .order_by(ChatTurn.id)
            ).all()
            if (t.text or "").strip()
        ]
        if db_turns:
            turns = db_turns

    vars_block: dict[str, Any] = {
        "name": f"FB-{row.id} {tag_label}",
        "thread": {"turns": turns or [row.question or snap.get("question") or ""]},
    }
    profile = _profile_block(snap)
    if profile:
        vars_block["profile"] = profile

    return {
        "description": f"FB-{row.id} 多轮差评：{tag_label}",
        "tags": ["inbox", "from_feedback", "long", *tags],
        "vars": vars_block,
        "meta": {
            "feedback_id": row.id,
            "tags": tags,
            "note": row.note or "",
            "format": "thread",
            "observed": _observed(row, snap),
            "promote_to": "cases-long.yaml",
        },
        "assert": [
            {
                "type": "javascript",
                "value": "file://assertions/shape-long.js",
            },
        ],
    }


def _case_doc(
    row: FeedbackEvent,
    *,
    format: FormatMode = "auto",
    session: Session | None = None,
) -> dict[str, Any]:
    snap = row.snapshot or {}
    kind = _resolve_format(session, row, snap, format)
    if kind == "thread":
        return _case_doc_thread(session, row, snap)
    return _case_doc_single(row, snap)


def export_inbox(out_dir: Path, *, format: FormatMode = "auto") -> list[Path]:
    init_db()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(FeedbackEvent)
                .where(FeedbackEvent.rating == "down")
                .where(FeedbackEvent.export_status == "pending")
                .order_by(FeedbackEvent.id)
            ).all()
        )
        for row in rows:
            doc = _case_doc(row, format=format, session=session)
            fmt = (doc.get("meta") or {}).get("format") or "single"
            slug = _slug(row.question)
            name = f"FB-{row.id}-{fmt}-{slug}.yaml"
            path = out_dir / name
            if fmt == "thread":
                header = (
                    "# inbox 多轮草稿：未审不进正式绿集。核对后拷进 cases-long.yaml。\n"
                    "# 轮次在 vars.thread.turns（勿写成顶层 vars.turns）。\n"
                    "# TODO: 人工/DeepSeek 补 thread / adopt / llm-rubric\n"
                )
            else:
                header = (
                    "# inbox 草稿：未审不进正式绿集。补全 assert 后拷进 cases.yaml。\n"
                    "# TODO: 人工/DeepSeek 补 branch / text / llm-rubric\n"
                )
            path.write_text(header + _dump_yaml(doc) + "\n", encoding="utf-8")
            row.export_status = "exported"
            session.add(row)
            written.append(path)
        session.commit()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Export pending downvotes to eval/inbox")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "eval" / "inbox",
        help="output directory for YAML drafts",
    )
    parser.add_argument(
        "--format",
        choices=("auto", "single", "thread"),
        default="auto",
        help="auto: ≥2 用户轮 → thread，否则 single；也可强制 single/thread",
    )
    args = parser.parse_args()
    paths = export_inbox(args.out, format=args.format)
    if not paths:
        print("no pending downvotes")
        return
    print(f"exported {len(paths)} case(s) → {args.out}")
    for path in paths:
        print(f"  {path.name}")


if __name__ == "__main__":
    main()
