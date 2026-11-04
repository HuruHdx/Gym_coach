"""按请求绑定当前用户，供 service / brain 层过滤数据。"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

from sqlmodel import select

if TYPE_CHECKING:
    from sqlmodel import Session

    from app.models import Profile

_current_user_id: ContextVar[int | None] = ContextVar("gym_current_user_id", default=None)


def set_current_user_id(user_id: int | None) -> None:
    _current_user_id.set(user_id)


def current_user_id() -> int | None:
    return _current_user_id.get()


def get_current_profile(session: Session) -> Profile | None:
    """JWT 用户只读自己的画像；APP_TOKEN 仍读第一条（评测兼容）。"""
    from app.models import Profile

    uid = current_user_id()
    if uid is not None:
        return session.exec(select(Profile).where(Profile.user_id == uid)).first()
    return session.exec(select(Profile).limit(1)).first()