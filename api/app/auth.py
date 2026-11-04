from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.models import User
from app.tenancy import set_current_user_id

_bearer = HTTPBearer(auto_error=False)

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
MIN_PASSWORD_LEN = 6
JWT_ALG = "HS256"


@dataclass(frozen=True)
class AuthContext:
    """鉴权结果。user_id 为空表示 APP_TOKEN（评测 / 脚本）。"""

    token: str
    user_id: int | None


def _jwt_secret() -> str:
    secret = (settings.jwt_secret or "").strip()
    if not secret:
        # 本地开发兜底；生产请设 JWT_SECRET（≥32 字节）
        secret = f"gym-coach-jwt:{settings.app_token}"
    # HS256 建议密钥 ≥ 32 bytes（RFC 7518）
    if len(secret.encode("utf-8")) < 32:
        secret = secret.ljust(32, "0")
    return secret


def normalize_phone(raw: str) -> str:
    phone = re.sub(r"\s+", "", (raw or "").strip())
    if phone.startswith("+86"):
        phone = phone[3:]
    return phone


def validate_phone(phone: str) -> str:
    phone = normalize_phone(phone)
    if not PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="手机号格式不对，请用 11 位大陆号")
    return phone


def validate_password(password: str) -> str:
    if len(password or "") < MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"密码至少 {MIN_PASSWORD_LEN} 位")
    if len(password) > 72:
        raise HTTPException(status_code=400, detail="密码太长")
    return password


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def issue_access_token(user_id: int) -> str:
    """签发用户 access JWT，客户端放进 Authorization: Bearer。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=max(1, settings.jwt_expire_days)),
        "typ": "access",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALG)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    if payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")
    sub = payload.get("sub")
    try:
        user_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_id


def require_auth(
    creds: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> AuthContext:
    """企业常规：校验请求头 Authorization: Bearer <token>。"""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = creds.credentials
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    # 评测 / 脚本机器口令（非用户 JWT）
    if token == settings.app_token:
        set_current_user_id(None)
        return AuthContext(token=token, user_id=None)

    user_id = decode_access_token(token)
    set_current_user_id(user_id)
    return AuthContext(token=token, user_id=user_id)


def require_token(auth: AuthContext = Depends(require_auth)) -> str:
    """兼容旧 Depends：只校验通过，返回凭证字符串。"""
    return auth.token


def bind_auth(auth: AuthContext = Depends(require_auth)) -> AuthContext:
    """同步路由专用：在接口所在线程再次绑定 user_id。

    FastAPI 会把 sync 依赖和 sync 接口丢进不同线程池工人，
    ContextVar 在依赖里 set 后接口里读不到，导致 user 过滤失效、旧数据串号。
    接口 Depends(bind_auth) 后，tenancy.current_user_id() 才可靠。
    """
    set_current_user_id(auth.user_id)
    return auth


def require_user(
    auth: AuthContext = Depends(bind_auth),
    session: Session = Depends(get_session),
) -> User:
    if auth.user_id is None:
        raise HTTPException(status_code=403, detail="需要用户登录")
    user = session.get(User, auth.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
