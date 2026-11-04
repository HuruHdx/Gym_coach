from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import AuthContext, bind_auth
from app.db import get_session
from app.models import Profile, ProfileHistory, utcnow
from app.schemas import ProfileCreate, ProfileOut, ProfileUpdate, WeightLogIn, WeightPoint
from app.tenancy import current_user_id

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


def _as_str_list(value: Any) -> list[str]:
    """SQLite / 旧 TEXT 列有时把 JSON 读成字符串 '[]'，这里统一成 list。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [raw] if raw not in ("[]", "null") else []
        if isinstance(parsed, list):
            return [str(x) for x in parsed if str(x).strip()]
        return []
    return []


def _out(p: Profile) -> ProfileOut:
    if getattr(p, "session_minutes", None) is None:
        p.session_minutes = 45
    p.preferences = _as_str_list(p.preferences)
    p.injuries = _as_str_list(p.injuries)
    p.avoid_exercises = _as_str_list(getattr(p, "avoid_exercises", None))
    p.avoid_foods = _as_str_list(p.avoid_foods)
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


def _get_profile(session: Session, auth: AuthContext) -> Profile | None:
    if auth.user_id is not None:
        return session.exec(select(Profile).where(Profile.user_id == auth.user_id)).first()
    return session.exec(select(Profile).limit(1)).first()


@router.get("", response_model=ProfileOut | None)
def get_profile(session: Session = Depends(get_session), auth: AuthContext = Depends(bind_auth)):
    p = _get_profile(session, auth)
    return _out(p) if p else None


@router.post("", response_model=ProfileOut)
def create_profile(
    body: ProfileCreate,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(bind_auth),
):
    existing = _get_profile(session, auth)
    if existing:
        raise HTTPException(status_code=409, detail="Profile already exists; use PATCH")
    data = body.model_dump()
    data["preferences"] = _clean_equipment(data.get("preferences"))
    data["injuries"] = _clean_tags(data.get("injuries"))
    data["avoid_foods"] = _clean_tags(data.get("avoid_foods"))
    data["avoid_exercises"] = _clean_tags(data.get("avoid_exercises") or [])
    if auth.user_id is not None:
        data["user_id"] = auth.user_id
    p = Profile(**data)
    session.add(p)
    session.flush()
    if p.weight_kg is not None:
        session.add(
            ProfileHistory(
                user_id=auth.user_id,
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
    auth: AuthContext = Depends(bind_auth),
):
    p = _get_profile(session, auth)
    if not p:
        raise HTTPException(status_code=404, detail="No profile")

    data = body.model_dump(exclude_unset=True)
    now = utcnow()

    for field in SCALAR_FIELDS:
        # height_cm / weight_kg 允许显式清空为 null；其余标量忽略 None
        if field not in data:
            continue
        if data[field] is None and field not in ("height_cm", "weight_kg"):
            continue
        old = getattr(p, field)
        new = data[field]
        if old != new:
            session.add(
                ProfileHistory(
                    user_id=auth.user_id,
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
def profile_history(session: Session = Depends(get_session), auth: AuthContext = Depends(bind_auth)):
    q = select(ProfileHistory)
    uid = auth.user_id if auth.user_id is not None else current_user_id()
    if uid is None:
        return []
    q = q.where(ProfileHistory.user_id == uid)
    rows = session.exec(q.order_by(ProfileHistory.id.desc()).limit(50)).all()
    return [
        {"id": r.id, "field": r.field, "old_value": r.old_value, "new_value": r.new_value, "created_at": r.created_at}
        for r in rows
    ]


@router.post("/weight", response_model=ProfileOut)
def log_weight(
    body: WeightLogIn,
    session: Session = Depends(get_session),
    auth: AuthContext = Depends(bind_auth),
):
    """记一笔体重：覆盖当前体重并写入变更历史（供趋势图）。"""
    p = _get_profile(session, auth)
    if not p:
        raise HTTPException(status_code=404, detail="No profile")
    old = p.weight_kg
    new = round(float(body.weight_kg), 1)
    if old != new:
        session.add(
            ProfileHistory(
                user_id=auth.user_id,
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
    auth: AuthContext = Depends(bind_auth),
):
    """体重曲线点：取历史入账，时间正序。"""
    lim = max(3, min(limit, 60))
    hist_q = select(ProfileHistory).where(ProfileHistory.field == "weight_kg")
    uid = auth.user_id if auth.user_id is not None else current_user_id()
    if uid is not None:
        hist_q = hist_q.where(ProfileHistory.user_id == uid)
    rows = session.exec(hist_q.order_by(ProfileHistory.id.desc()).limit(lim)).all()
    points: list[WeightPoint] = []
    for r in reversed(rows):
        try:
            w = float(r.new_value)
        except (TypeError, ValueError):
            continue
        points.append(WeightPoint(weight_kg=w, recorded_at=r.created_at))
    # 无历史时仅在已填体重时垫一点，避免空图；未填不伪造
    if not points:
        p = _get_profile(session, auth)
        if p and p.weight_kg is not None:
            points.append(WeightPoint(weight_kg=p.weight_kg, recorded_at=p.updated_at))
    return points


@router.delete("")
def delete_profile(session: Session = Depends(get_session), auth: AuthContext = Depends(bind_auth)):
    """Clear profile so onboarding can run again (dev / reset)."""
    p = _get_profile(session, auth)
    if p:
        session.delete(p)
        session.commit()
    return {"ok": True}
