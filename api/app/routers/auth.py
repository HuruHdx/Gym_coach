from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import (
    AuthContext,
    bind_auth,
    hash_password,
    issue_access_token,
    require_user,
    validate_password,
    validate_phone,
    verify_password,
)
from app.config import settings
from app.db import get_session
from app.models import User
from app.schemas import AuthLoginIn, AuthRegisterIn, AuthTokenOut, UserOut, UserUpdate

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id or 0, phone=user.phone, display_name=user.display_name)


def _token_out(user: User, access_token: str) -> AuthTokenOut:
    return AuthTokenOut(access_token=access_token, token_type="bearer", user=_user_out(user))


@router.post("/register", response_model=UserOut)
def register(body: AuthRegisterIn, session: Session = Depends(get_session)):
    """只建账号，不发 JWT；注册成功后须再调 /login。

    新账号不接管旧画像 / 旧训练——每人自己走 onboarding。
    """
    phone = validate_phone(body.phone)
    password = validate_password(body.password)
    existing = session.exec(select(User).where(User.phone == phone)).first()
    if existing:
        raise HTTPException(status_code=409, detail="该手机号已注册，请直接登录")

    name = (body.display_name or "").strip() or None
    user = User(phone=phone, password_hash=hash_password(password), display_name=name)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_out(user)


@router.post("/login", response_model=AuthTokenOut)
def login(body: AuthLoginIn, session: Session = Depends(get_session)):
    phone = validate_phone(body.phone)
    user = session.exec(select(User).where(User.phone == phone)).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="手机号或密码不对")
    assert user.id is not None
    return _token_out(user, issue_access_token(user.id))


@router.post("/logout")
def logout(_: AuthContext = Depends(bind_auth)):
    """JWT 无服务端会话；客户端丢弃 token 即可。此接口用于统一约定。"""
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)):
    return _user_out(user)


@router.patch("/me", response_model=UserOut)
def update_me(
    body: UserUpdate,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
):
    if "display_name" in body.model_fields_set:
        name = (body.display_name or "").strip() or None
        if name and len(name) > 40:
            raise HTTPException(status_code=400, detail="昵称最多 40 字")
        user.display_name = name
        session.add(user)
        session.commit()
        session.refresh(user)
    return _user_out(user)


@router.get("/verify")
def verify(auth: AuthContext = Depends(bind_auth)):
    return {
        "ok": True,
        "app": settings.app_name,
        "user_id": auth.user_id,
    }
