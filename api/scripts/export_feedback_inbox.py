"""把 pending 差评导出成 eval/inbox YAML 草稿（不进正式绿集）。

用法（在 api/ 下）:
  uv run python scripts/export_feedback_inbox.py
  uv run python scripts/export_feedback_inbox.py --out ../eval/inbox
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import engine, init_db  # noqa: E402
from app.models import FeedbackEvent  # noqa: E402


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


def _case_doc(row: FeedbackEvent) -> dict[str, Any]:
    snap = row.snapshot or {}
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
    profile = snap.get("profile")
    if isinstance(profile, dict) and profile:
        vars_block["profile"] = profile

    intent = snap.get("intent") if isinstance(snap.get("intent"), dict) else {}
    observed = {
        "topic": intent.get("topic"),
        "domain": intent.get("domain"),
        "route": snap.get("route"),
        "branch": snap.get("branch"),
        "answer": row.answer or snap.get("answer") or "",
    }
    return {
        "description": f"FB-{row.id} 用户差评：{tag_label}",
        "tags": ["inbox", "from_feedback", *tags],
        "vars": vars_block,
        "meta": {
            "feedback_id": row.id,
            "tags": tags,
            "note": row.note or "",
            "observed": observed,
        },
        "assert": [
            {
                "type": "javascript",
                "value": "file://assertions/shape.js",
            },
        ],
    }


def export_inbox(out_dir: Path) -> list[Path]:
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
            name = f"FB-{row.id}-{_slug(row.question)}.yaml"
            path = out_dir / name
            doc = _case_doc(row)
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
    args = parser.parse_args()
    paths = export_inbox(args.out)
    if not paths:
        print("no pending downvotes")
        return
    print(f"exported {len(paths)} case(s) → {args.out}")
    for path in paths:
        print(f"  {path.name}")


if __name__ == "__main__":
    main()
