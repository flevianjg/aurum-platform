"""Generate cryptographic material for .env.

Run from repo root:

    python scripts/generate_keys.py

Outputs:
  * MASTER_KEY  — 32 bytes, base64-encoded (libsodium SecretBox key)
  * JWT_SECRET  — 64 bytes, base64-encoded (HS256 signing key)
  * POSTGRES_PASSWORD — 32 bytes, urlsafe-base64 (suggested DB password)

Paste each value into your .env. Never commit the .env file.
"""

from __future__ import annotations

import base64
import secrets


def main() -> None:
    master_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    jwt_secret = base64.b64encode(secrets.token_bytes(64)).decode("ascii")
    pg_password = secrets.token_urlsafe(32)

    print("# Paste these into your .env\n")
    print(f"MASTER_KEY={master_key}")
    print(f"JWT_SECRET={jwt_secret}")
    print(f"POSTGRES_PASSWORD={pg_password}")
    print(
        "\n# Remember to update DATABASE_URL with the new POSTGRES_PASSWORD:\n"
        f"# DATABASE_URL=postgresql+asyncpg://aurum:{pg_password}@postgres:5432/aurum"
    )


if __name__ == "__main__":
    main()
