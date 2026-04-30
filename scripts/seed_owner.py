"""Seed the OWNER user record from .env values.

Idempotent: running it multiple times will not create duplicates.
Does NOT create a passkey — Flevian registers his own via the WebAuthn API
after first deploy.

Run inside the backend container:

    docker compose run --rm backend python /app/../scripts/seed_owner.py

…or after exec-ing in:

    docker compose exec backend python -m scripts.seed_owner

This script imports the backend app, so it must run with the backend's
PYTHONPATH (i.e. inside the container, or with `cd backend && python ../scripts/seed_owner.py`).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the script work whether invoked from repo root or inside the container
# (where scripts/ is mounted at /app/scripts and /app is the working dir).
_HERE = Path(__file__).resolve().parent
for candidate in (_HERE.parent / "backend", _HERE.parent):
    if (candidate / "app").is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
        break

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models import User, UserRole  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


async def seed() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        existing = (
            await session.execute(
                select(User).where(User.email == settings.OWNER_EMAIL.lower())
            )
        ).scalar_one_or_none()

        if existing is not None:
            print(f"OWNER already exists: id={existing.id} email={existing.email}")
            await session.rollback()
            return

        user = User(
            email=settings.OWNER_EMAIL.lower(),
            display_name=settings.OWNER_DISPLAY_NAME,
            role=UserRole.OWNER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"OWNER created: id={user.id} email={user.email}")


if __name__ == "__main__":
    asyncio.run(seed())
