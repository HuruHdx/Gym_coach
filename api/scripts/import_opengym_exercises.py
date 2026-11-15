"""Import enriched openGym JSON into DB + seed start/end media + aliases.

Usage (from api/):
  uv run python scripts/import_opengym_exercises.py
  uv run python scripts/import_opengym_exercises.py --json path/to.json
  uv run python scripts/import_opengym_exercises.py --no-replace
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
from app.models import Exercise, ExerciseAlias, ExerciseMedia, utcnow  # noqa: E402

DEFAULT_JSON = ROOT / "assets" / "opengym" / "opengym_exercises_enriched.json"
LEGACY_JSON = ROOT / "assets" / "opengym" / "opengym_exercises_with_media.json"


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return list(value)
    return []


def _as_dict(value: object) -> dict:
    if isinstance(value, dict):
        return dict(value)
    return {}


def row_to_model(raw: dict) -> Exercise:
    return Exercise(
        id=str(raw.get("id") or ""),
        name_en=raw.get("name_en") or "",
        name_zh=raw.get("name_zh") or "",
        body_part=raw.get("body_part"),
        equipment=raw.get("equipment"),
        target=raw.get("target"),
        secondary_muscles=_as_list(raw.get("secondary_muscles")),
        category=raw.get("category"),
        description_en=raw.get("description_en"),
        description_zh=raw.get("description_zh"),
        instructions_en=_as_list(raw.get("instructions_en")),
        instructions_zh=_as_list(raw.get("instructions_zh")),
        image_start=raw.get("image_start"),
        image_end=raw.get("image_end"),
        fdb_id=raw.get("fdb_id"),
        text_source=raw.get("text_source"),
        female_variant=raw.get("female_variant"),
        variant_of=raw.get("variant_of"),
        muscle=raw.get("muscle") or "全身",
        roles=_as_list(raw.get("roles")),
        modality=raw.get("modality") or "抗阻",
        gear=raw.get("gear") or "器械",
        coach_core=bool(raw.get("coach_core")),
        sub_region=raw.get("sub_region"),
        movement_pattern=raw.get("movement_pattern"),
        joint_stress=_as_dict(raw.get("joint_stress")),
        cues_zh=_as_list(raw.get("cues_zh")),
        common_mistakes_zh=_as_list(raw.get("common_mistakes_zh")),
        is_valid_exercise=bool(raw.get("is_valid_exercise", True)),
        needs_review=False,
        updated_at=utcnow(),
    )


def _seed_media(session: Session, exercise: Exercise) -> int:
    """Upsert published start/end seed rows from image_* paths."""
    written = 0
    for role, path in (("start", exercise.image_start), ("end", exercise.image_end)):
        if not path:
            continue
        existing = session.exec(
            select(ExerciseMedia).where(
                ExerciseMedia.exercise_id == exercise.id,
                ExerciseMedia.role == role,
                ExerciseMedia.source == "seed",
            )
        ).first()
        if existing:
            existing.url = path
            existing.status = "published"
            existing.meta = {"seed": True}
            session.add(existing)
        else:
            session.add(
                ExerciseMedia(
                    exercise_id=exercise.id,
                    role=role,
                    url=path,
                    status="published",
                    source="seed",
                    meta={"seed": True},
                )
            )
            written += 1
    return written


def _seed_aliases(session: Session, exercise_id: str, aliases: list[str]) -> int:
    written = 0
    seen: set[str] = set()
    for raw in aliases:
        alias = str(raw or "").strip()
        if not alias or alias in seen:
            continue
        seen.add(alias)
        existing = session.exec(
            select(ExerciseAlias).where(
                ExerciseAlias.exercise_id == exercise_id,
                ExerciseAlias.alias == alias,
            )
        ).first()
        if existing:
            existing.status = "published"
            session.add(existing)
            continue
        session.add(
            ExerciseAlias(
                exercise_id=exercise_id,
                alias=alias,
                status="published",
            )
        )
        written += 1
    return written


def _legacy_name_map() -> dict[str, str]:
    """Keep previous name_zh as alias when enriched renames an exercise."""
    if not LEGACY_JSON.exists():
        return {}
    try:
        legacy = json.loads(LEGACY_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    if isinstance(legacy, list):
        for row in legacy:
            if isinstance(row, dict) and row.get("id") and row.get("name_zh"):
                out[str(row["id"])] = str(row["name_zh"]).strip()
    return out


def import_exercises(json_path: Path, *, replace: bool = True) -> dict[str, int]:
    raw_list = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(raw_list, list):
        raise SystemExit(f"Expected list in {json_path}")

    init_db()
    legacy_names = _legacy_name_map()
    models = [row_to_model(r) for r in raw_list if isinstance(r, dict) and r.get("id")]
    alias_map: dict[str, list[str]] = {}
    for r in raw_list:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        eid = str(r["id"])
        aliases = [str(a).strip() for a in (r.get("aliases") or []) if str(a).strip()]
        old_name = legacy_names.get(eid, "")
        new_name = str(r.get("name_zh") or "").strip()
        if old_name and new_name and old_name != new_name and old_name not in aliases:
            aliases.append(old_name)
        alias_map[eid] = aliases

    media_new = 0
    alias_new = 0
    with Session(engine) as session:
        if replace:
            for row in session.exec(select(ExerciseMedia)).all():
                session.delete(row)
            for row in session.exec(select(ExerciseAlias)).all():
                session.delete(row)
            for row in session.exec(select(Exercise)).all():
                session.delete(row)
            session.commit()

        for m in models:
            session.merge(m)
        session.commit()

        for m in models:
            media_new += _seed_media(session, m)
            alias_new += _seed_aliases(session, m.id, alias_map.get(m.id, []))
        session.commit()

    return {
        "exercises": len(models),
        "media_seeded": media_new,
        "aliases_seeded": alias_new,
        "coach_core": sum(1 for m in models if m.coach_core),
        "with_start": sum(1 for m in models if m.image_start),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import enriched openGym exercises")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="Upsert without wiping exercises/media/aliases first",
    )
    args = parser.parse_args()
    json_path = args.json
    if json_path is None:
        json_path = DEFAULT_JSON if DEFAULT_JSON.exists() else LEGACY_JSON
    if not json_path.exists():
        raise SystemExit(f"JSON not found: {json_path}")
    stats = import_exercises(json_path, replace=not args.no_replace)
    print(f"Imported from {json_path}")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
