"""Credential encryption helpers backed by libsodium SecretBox.

Public API:
    encrypt_credentials(plaintext: dict) -> tuple[bytes, bytes]
    decrypt_credentials(ciphertext: bytes, nonce: bytes) -> dict

The plaintext dict is JSON-serialized with sort_keys=True before encryption so
re-encrypting the same logical credentials produces deterministic plaintext
(but different ciphertext, since each call generates a fresh 24-byte nonce).

Master key comes from settings.MASTER_KEY (validated at startup to be exactly
32 bytes after base64 decoding). If the key is missing or wrong-length the app
refuses to start — see config.Settings._validate_master_key.

Logging policy: never log plaintext, ciphertext, or nonces. Operations log
only the operation tag (e.g. "credential_op:encrypt").
"""

from __future__ import annotations

import json
import logging
from typing import Any

from nacl import secret, utils
from nacl.exceptions import CryptoError as NaClCryptoError

from app.config import get_settings

logger = logging.getLogger(__name__)

NONCE_SIZE = secret.SecretBox.NONCE_SIZE  # 24 bytes


class CryptoError(Exception):
    """Raised on tamper detection, wrong key, or malformed payload."""


def _box() -> secret.SecretBox:
    return secret.SecretBox(get_settings().master_key_bytes)


def encrypt_credentials(plaintext: dict[str, Any]) -> tuple[bytes, bytes]:
    """Encrypt a credentials dict with a freshly generated nonce.

    Returns (ciphertext, nonce). The ciphertext is the libsodium SecretBox
    ciphertext WITHOUT the prepended nonce — the nonce is returned separately
    so it can be stored in its own column.
    """
    serialized = json.dumps(plaintext, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    nonce = utils.random(NONCE_SIZE)
    encrypted = _box().encrypt(serialized, nonce)
    logger.debug("credential_op:encrypt")
    # encrypted.ciphertext is just the boxed bytes; encrypted.nonce is the same
    # nonce we passed in. Store nonce separately for clarity at the schema level.
    return encrypted.ciphertext, nonce


def decrypt_credentials(ciphertext: bytes, nonce: bytes) -> dict[str, Any]:
    """Decrypt a previously-encrypted credentials blob.

    Raises CryptoError on tamper, wrong key, malformed JSON, or wrong nonce
    size. Never includes ciphertext/nonce in error messages.
    """
    if len(nonce) != NONCE_SIZE:
        raise CryptoError("nonce has wrong size")
    try:
        plaintext = _box().decrypt(ciphertext, nonce)
    except NaClCryptoError as exc:
        raise CryptoError("decryption failed (tamper, wrong key, or bad nonce)") from exc
    try:
        result = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CryptoError("decrypted payload is not valid JSON") from exc
    if not isinstance(result, dict):
        raise CryptoError("decrypted payload is not a JSON object")
    logger.debug("credential_op:decrypt")
    return result
