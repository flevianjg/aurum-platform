"""SecretBox crypto helpers."""

from __future__ import annotations

import base64

import pytest

from app.core.crypto import (
    NONCE_SIZE,
    CryptoError,
    decrypt_credentials,
    encrypt_credentials,
)


def test_encrypt_decrypt_round_trip() -> None:
    plaintext = {"account_id": "abc", "api_token": "tok-123", "environment": "practice"}
    ciphertext, nonce = encrypt_credentials(plaintext)
    assert isinstance(ciphertext, bytes) and isinstance(nonce, bytes)
    assert len(nonce) == NONCE_SIZE
    assert decrypt_credentials(ciphertext, nonce) == plaintext


def test_two_encryptions_use_different_nonces() -> None:
    plaintext = {"account_id": "x", "api_token": "y", "environment": "practice"}
    c1, n1 = encrypt_credentials(plaintext)
    c2, n2 = encrypt_credentials(plaintext)
    assert n1 != n2
    assert c1 != c2  # different nonce → different ciphertext even for same plaintext


def test_decrypt_with_wrong_nonce_size_raises() -> None:
    plaintext = {"a": "b"}
    ciphertext, _ = encrypt_credentials(plaintext)
    with pytest.raises(CryptoError, match="nonce has wrong size"):
        decrypt_credentials(ciphertext, b"too-short")


def test_decrypt_tampered_ciphertext_raises() -> None:
    plaintext = {"account_id": "x", "api_token": "y", "environment": "practice"}
    ciphertext, nonce = encrypt_credentials(plaintext)
    tampered = bytes([ciphertext[0] ^ 0x01]) + ciphertext[1:]
    with pytest.raises(CryptoError):
        decrypt_credentials(tampered, nonce)


def test_decrypt_with_wrong_key_raises(monkeypatch) -> None:
    plaintext = {"account_id": "x", "api_token": "y", "environment": "practice"}
    ciphertext, nonce = encrypt_credentials(plaintext)

    # Swap settings master_key_bytes for a different valid 32-byte key
    from app.config import get_settings

    settings = get_settings()
    different_key = base64.b64encode(b"X" * 32).decode("ascii")
    original = settings.MASTER_KEY
    monkeypatch.setattr(settings, "MASTER_KEY", different_key)
    try:
        with pytest.raises(CryptoError):
            decrypt_credentials(ciphertext, nonce)
    finally:
        monkeypatch.setattr(settings, "MASTER_KEY", original)
