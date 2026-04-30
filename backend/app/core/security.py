"""Security primitives: JWT issuance/verification, refresh-token hashing,
credential encryption (libsodium SecretBox), and password hashing (defense
in depth — passkeys are primary, but we keep the primitive available)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from jose import JWTError, jwt
from nacl import secret, utils

from app.config import get_settings


_settings = get_settings()
_password_hasher = PasswordHasher()
_JWT_ALG = "HS256"


# ---------- JWT ----------


def create_access_token(*, user_id: uuid.UUID, role: str) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=_settings.JWT_ACCESS_TTL_SECONDS)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(16),
        "typ": "access",
    }
    token = jwt.encode(payload, _settings.JWT_SECRET, algorithm=_JWT_ALG)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _settings.JWT_SECRET, algorithms=[_JWT_ALG])
    except JWTError as exc:
        raise ValueError(f"invalid token: {exc}") from exc
    if payload.get("typ") != "access":
        raise ValueError("wrong token type")
    return payload


# ---------- Refresh tokens ----------


def generate_refresh_token() -> tuple[str, bytes, datetime]:
    """Returns (opaque_token, sha256_hash, expires_at)."""
    raw = secrets.token_urlsafe(48)  # ~64 chars, ~384 bits entropy
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=_settings.JWT_REFRESH_TTL_SECONDS
    )
    return raw, digest, expires_at


def hash_refresh_token(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


# ---------- Credential encryption (broker_accounts.encrypted_credentials) ----------


def _box() -> secret.SecretBox:
    return secret.SecretBox(_settings.master_key_bytes)


def encrypt_credentials(plaintext: bytes) -> tuple[bytes, bytes]:
    """SecretBox-encrypt a credential blob. Returns (ciphertext, nonce)."""
    nonce = utils.random(secret.SecretBox.NONCE_SIZE)
    ciphertext = _box().encrypt(plaintext, nonce).ciphertext
    return ciphertext, nonce


def decrypt_credentials(ciphertext: bytes, nonce: bytes) -> bytes:
    return _box().decrypt(ciphertext, nonce)


# ---------- Password hashing (kept for defense-in-depth, not used in Phase 1) ----------


def hash_password(plaintext: str) -> str:
    return _password_hasher.hash(plaintext)


def verify_password(hashed: str, plaintext: str) -> bool:
    try:
        return _password_hasher.verify(hashed, plaintext)
    except Exception:
        return False
