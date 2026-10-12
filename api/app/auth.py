from __future__ import annotations

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer = HTTPBearer(auto_error=False)


def require_token(
    creds: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if creds.credentials != settings.app_token:
        raise HTTPException(status_code=403, detail="Invalid token")
    return creds.credentials
