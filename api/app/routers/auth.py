from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_token
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/verify")
def verify(_: str = Depends(require_token)):
    return {"ok": True, "app": settings.app_name}
