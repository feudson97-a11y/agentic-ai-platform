"""
API v1 — Authentication Router
JWT-based auth: login, refresh, logout.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from pydantic import BaseModel

from apps.backend.core.config import settings

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


def _create_token(sub: str, expires_delta: timedelta, token_type: str = "access") -> str:
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    # Stub: replace with real user lookup + bcrypt verification
    if body.username != "admin" or body.password != "changeme":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access = _create_token(body.username, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    refresh = _create_token(body.username, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh")
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_token: str) -> TokenResponse:
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise ValueError("Wrong token type")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    access = _create_token(payload["sub"], timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    new_refresh = _create_token(payload["sub"], timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh")
    return TokenResponse(access_token=access, refresh_token=new_refresh, expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
