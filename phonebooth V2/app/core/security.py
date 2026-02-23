from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import HTTPException, status
from jose import jwt

from app.core.config import get_settings

settings = get_settings()

_jwks_cache: dict[str, Any] | None = None
_jwks_cache_expiry: datetime | None = None


async def _get_jwks() -> dict[str, Any]:
    global _jwks_cache, _jwks_cache_expiry
    now = datetime.now(UTC)

    if _jwks_cache and _jwks_cache_expiry and now < _jwks_cache_expiry:
        return _jwks_cache

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(settings.supabase_jwks_url)
        response.raise_for_status()
        data = response.json()

    _jwks_cache = data
    _jwks_cache_expiry = now + timedelta(minutes=30)
    return data


async def verify_supabase_jwt(token: str) -> dict[str, Any]:
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header") from exc

    jwks = await _get_jwks()
    kid = unverified_header.get("kid")
    keys = jwks.get("keys", [])
    matching_key = next((key for key in keys if key.get("kid") == kid), None)

    if not matching_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No matching public key")

    try:
        payload = jwt.decode(
            token,
            matching_key,
            algorithms=[matching_key.get("alg", "RS256")],
            audience=settings.supabase_jwt_audience,
            issuer=f"{settings.supabase_url}/auth/v1",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token verification failed") from exc

    return payload
