"""Passwords, access tokens and refresh tokens."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import AppError

_ph = PasswordHasher()  # argon2id with library defaults
_DUMMY_HASH = _ph.hash("timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    s = get_settings()
    ttl = s.access_token_ttl_minutes * 60
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iss": s.jwt_issuer, "iat": now, "nbf": now,
               "exp": now + timedelta(seconds=ttl), "typ": "access",
               "iat_ms": int(now.timestamp() * 1000)}  # sub-second issue time: see deps.get_principal
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm="HS256"), ttl


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def decode_access_token(token: str) -> dict:
    """Return claims for a valid token. Raises AppError(401) otherwise."""
    s = get_settings()
    try:
        if s.auth_mode == "local":
            claims = jwt.decode(token, s.jwt_secret.get_secret_value(), algorithms=["HS256"], issuer=s.jwt_issuer,
                                options={"require": ["exp", "sub", "iat"]})
            if claims.get("typ") != "access":
                raise jwt.InvalidTokenError("wrong token type")
            return claims
        # external_jwt: an identity provider such as Supabase Auth issues the token.
        key = _jwks_client(s.external_jwks_url).get_signing_key_from_jwt(token).key  # type: ignore[arg-type]
        return jwt.decode(token, key, algorithms=["RS256", "ES256"], audience=s.external_jwt_audience,
                          issuer=s.external_jwt_issuer, options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        raise AppError(401, "invalid_token", "Unauthenticated", "Sign in again.",
                       headers={"WWW-Authenticate": "Bearer"}) from None
