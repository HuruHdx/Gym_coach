from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import require_token
from app.db import get_session
from app.models import Profile, ProfileHistory, utcnow
from app.schemas import ProfileCreate, ProfileOut, ProfileUpdate, WeightLogIn, WeightPoint

router = APIRouter(prefix="/api/profile", tags=["profile"])

SCALAR_FIELDS = (
    "goal",
    "experience",
    "weight_kg",
    "height_cm",
    "days_per_week",
    "session_minutes",
    "protein_target_g",
    "calorie_target",
)

ALLOWED_EQUIPMENT = {"器械", "自由重量", "绳索", "自重"}


def _out(p: Profile) -> ProfileOut:
    if getattr(p, "session_minutes", None) is None:
        p.session_minutes = 45
    if p.preferences is None:
        p.preferences = []
    if p.injuries is None:
        p.injuries = []
    return ProfileOut.model_validate(p, from_attributes=True)


def _clean_tags(items: list[str] | None) -> list[str]:
    out: list[str] = []
    for x in items or []:
        v = str(x).strip()
        if v and v not in out:
            out.append(v)
    return out


def _clean_equipment(items: list[str] | None) -> list[str]:
    return [x for x in _clean_tags(items) if x in ALLOWED_EQUIPMENT]


def _merge_list(current: list[str], add: list[str], remove: list[str]) -> list[str]:
    s = list(current or [])
    for x in add:
        x = x.strip()
        if x and x not in s:
            s.append(x)
    remove_set = {r.strip() for r in remove}
    return [x for x in s if x not in remove_set]


@router.get("", response_model=ProfileOut | None)
def get_profile(session: Session = Depends(get_session), _: str = Depends(require_token)):
    return session.exec(select(Profile).limit(1)).first()


@router.post("", response_model=ProfileOut)
def create_profile(
    body: ProfileCreate,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    existing = session.exec(select(Profile).limit(1)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Profile already exists; use PATCH")
    data = body.model_dump()
    data["preferences"] = _clean_equipment(data.get("preferences"))
    data["injuries"] = _clean_tags(data.get("injuries"))
    data["avoid_foods"] = _clean_tags(data.get("avoid_foods"))
    p = Profile(**data)
    session.add(p)
    session.flush()
    session.add(
        ProfileHistory(
            field="weight_kg",
            old_value="",
            new_value=str(p.weight_kg),
        )
    )
    session.commit()
    session.refresh(p)
    return _out(p)


@router.patch("", response_model=ProfileOut)
def update_profile(
    body: ProfileUpdate,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    p = session.exec(select(Profile).limit(1)).first()
    if not p:
        raise HTTPException(status_code=404, detail="No profile")

    data = body.model_dump(exclude_unset=True)
    now = utcnow()

    for field in SCALAR_FIELDS:
        # height_cm 允许显式清空为 null；其余标量忽略 None
        if field not in data:
            continue
        if data[field] is None and field != "height_cm":
            continue
        old = getattr(p, field)
        new = data[field]
        if old != new:
            session.add(
                ProfileHistory(
                    field=field,
                    old_value=str(getattr(old, "value", old)),
                    new_value=str(getattr(new, "value", new)),
                )
            )
            setattr(p, field, new)

    if body.injuries is not None:
        p.injuries = _clean_tags(body.injuries)
    else:
        p.injuries = _merge_list(p.injuries, body.injuries_add, body.injuries_remove)

    if body.preferences is not None:
        p.preferences = _clean_equipment(body.preferences)
    else:
        p.preferences = _clean_equipment(
            _merge_list(p.preferences, body.preferences_add, body.preferences_remove)
        )

    p.avoid_foods = _merge_list(p.avoid_foods, body.avoid_foods_add, body.avoid_foods_remove)
    p.updated_at = now
    session.add(p)
    session.commit()
    session.refresh(p)
    return _out(p)


@router.get("/history")
def profile_history(session: Session = Depends(get_session), _: str = Depends(require_token)):
    rows = session.exec(select(ProfileHistory).order_by(ProfileHistory.id.desc()).limit(50)).all()
    return [
        {"id": r.id, "field": r.field, "old_value": r.old_value, "new_value": r.new_value, "created_at": r.created_at}
        for r in rows
    ]


@router.post("/weight", response_model=ProfileOut)
def log_weight(
    body: WeightLogIn,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    """记一笔体重：覆盖当前体重并写入变更历史（供趋势图）。"""
    p = session.exec(select(Profile).limit(1)).first()
    if not p:
        raise HTTPException(status_code=404, detail="No profile")
    old = p.weight_kg
    new = round(float(body.weight_kg), 1)
    if old != new:
        session.add(
            ProfileHistory(
                field="weight_kg",
                old_value=str(old),
                new_value=str(new),
            )
        )
        p.weight_kg = new
        p.updated_at = utcnow()
        session.add(p)
        session.commit()
        session.refresh(p)
    return _out(p)


@router.get("/weight-history", response_model=list[WeightPoint])
def weight_history(
    limit: int = 14,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    """体重曲线点：取历史入账，时间正序。"""
    lim = max(3, min(limit, 60))
    rows = session.exec(
        select(ProfileHistory)
        .where(ProfileHistory.field == "weight_kg")
        .order_by(ProfileHistory.id.desc())
        .limit(lim)
    ).all()
    points: list[WeightPoint] = []
    for r in reversed(rows):
        try:
            w = float(r.new_value)
        except (TypeError, ValueError):
            continue
        points.append(WeightPoint(weight_kg=w, recorded_at=r.created_at))
    # 无历史时用当前画像垫一点，避免空图
    if not points:
        p = session.exec(select(Profile).limit(1)).first()
        if p:
            points.append(WeightPoint(weight_kg=p.weight_kg, recorded_at=p.updated_at))
    return points


@router.delete("")
def delete_profile(session: Session = Depends(get_session), _: str = Depends(require_token)):
    """Clear profile so onboarding can run again (dev / reset)."""
    p = session.exec(select(Profile).limit(1)).first()
    if p:
        session.delete(p)
        session.commit()
    return {"ok": True}
