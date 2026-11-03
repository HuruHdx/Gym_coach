"""Import openGym exercise JSON into Postgres (or whatever DATABASE_URL points to).

Usage (from api/):
  uv run python scripts/import_opengym_exercises.py
  uv run python scripts/import_opengym_exercises.py --json path/to.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import engine, init_db  # noqa: E402
from app.exercise_mapping import enrich_raw  # noqa: E402
from app.models import Exercise  # noqa: E402

DEFAULT_JSON = ROOT / "assets" / "opengym" / "opengym_exercises_with_media.json"


def row_to_model(raw: dict) -> Exercise:
    enriched = enrich_raw(raw)
    return Exercise(
        id=str(enriched.get("id") or ""),
        name_en=enriched.get("name_en") or "",
        name_zh=enriched.get("name_zh") or "",
        body_part=enriched.get("body_part"),
        equipment=enriched.get("equipment"),
        target=enriched.get("target"),
        secondary_muscles=list(enriched.get("secondary_muscles") or []),
        category=enriched.get("category"),
        description_en=enriched.get("description_en"),
        description_zh=enriched.get("description_zh"),
        instructions_en=list(enriched.get("instructions_en") or []),
        instructions_zh=list(enriched.get("instructions_zh") or []),
        image_start=enriched.get("image_start"),
        image_end=enriched.get("image_end"),
        fdb_id=enriched.get("fdb_id"),
        text_source=enriched.get("text_source"),
        female_variant=enriched.get("female_variant"),
        variant_of=enriched.get("variant_of"),
        muscle=enriched["muscle"],
        roles=list(enriched["roles"]),
        modality=enriched["modality"],
        gear=enriched["gear"],
        coach_core=bool(enriched.get("coach_core")),
    )


def import_exercises(json_path: Path, *, replace: bool = True) -> int:
    raw_list = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(raw_list, list):
        raise SystemExit(f"Expected list in {json_path}")
    init_db()
    models = [row_to_model(r) for r in raw_list if isinstance(r, dict) and r.get("id")]
    with Session(engine) as session:
        if replace:
            existing = session.exec(select(Exercise)).all()
            for row in existing:
                session.delete(row)
            session.commit()
        for m in models:
            session.merge(m)
        session.commit()
    return len(models)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import openGym exercises")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--no-replace", action="store_true", help="Upsert without wiping table first")
    args = parser.parse_args()
    if not args.json.exists():
        raise SystemExit(f"JSON not found: {args.json}")
    n = import_exercises(args.json, replace=not args.no_replace)
    print(f"Imported {n} exercises from {args.json}")


if __name__ == "__main__":
    main()
