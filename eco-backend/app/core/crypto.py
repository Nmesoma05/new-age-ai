"""Encryption of third-party credentials at rest (Fernet: AES-128-CBC + HMAC-SHA256).

Key rotation: CREDENTIALS_ENCRYPTION_KEY may hold several comma-separated keys. The FIRST key encrypts; every key
can decrypt (MultiFernet). To rotate: put a new key first, deploy, run `rotate_blob` over stored rows (or let
`needs_rotation` re-encrypt on next use), then remove the old key.
Recommendation for production: wrap these keys with a cloud KMS (envelope encryption).
"""
from __future__ import annotations

import json
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet

from app.core.config import get_settings


@lru_cache
def _keys() -> tuple[Fernet, ...]:
    raw = get_settings().credentials_encryption_key.get_secret_value()
    keys = tuple(Fernet(k.strip().encode()) for k in raw.split(",") if k.strip())
    if not keys:
        raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY is empty")
    return keys


@lru_cache
def _fernet() -> MultiFernet:
    return MultiFernet(list(_keys()))


def current_key_version() -> int:
    """A version number for the primary key: the number of keys configured (bump by adding a key first)."""
    return len(_keys())


def encrypt_json(data: dict) -> bytes:
    return _fernet().encrypt(json.dumps(data, separators=(",", ":")).encode())


def decrypt_json(blob: bytes) -> dict:
    return json.loads(_fernet().decrypt(bytes(blob)))


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(blob: bytes) -> bytes:
    return _fernet().decrypt(bytes(blob))


def rotate_blob(blob: bytes) -> bytes:
    """Re-encrypt under the primary key (no-op content-wise)."""
    return _fernet().rotate(bytes(blob))
