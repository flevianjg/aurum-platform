"""Pytest fixtures.

Strategy:
* A session-scoped fixture creates a dedicated test database (defaults to
  '<POSTGRES_DB>_test' if TEST_DATABASE_URL is unset), runs migrations once,
  and tears down at the end of the session.
* A function-scoped fixture truncates user-data tables between tests so each
  test starts from a clean slate without paying the migration cost again.
* `client` provides an httpx AsyncClient wired to the FastAPI app via
  ASGITransport — no real network involved.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


# ---------------------------------------------------------------------
# Compute the test DB URL BEFORE app modules import config.get_settings,
# so app.db.session binds to the right database.
# ---------------------------------------------------------------------


def _derive_test_db_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = os.environ["DATABASE_URL"]
    parsed = urlparse(base)
    new_path = parsed.path.rstrip("/") + "_test"
    return urlunparse(parsed._replace(path=new_path))


TEST_DB_URL = _derive_test_db_url()
os.environ["DATABASE_URL"] = TEST_DB_URL  # rebind app engine to test DB

# Now safe to import app modules
from app.db.models import (  # noqa: E402
    AuditLog,
    BrokerAccount,
    Passkey,
    RefreshToken,
    User,
)
from app.main import create_app  # noqa: E402


def _admin_url(test_url: str) -> tuple[str, str]:
    """Returns (admin-connection-url-to-postgres-db, test-db-name)."""
    parsed = urlparse(test_url.replace("+asyncpg", ""))
    db_name = parsed.path.lstrip("/")
    admin = urlunparse(parsed._replace(path="/postgres"))
    return admin, db_name


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_database() -> AsyncIterator[None]:
    """Drop & recreate the test DB once per session, run migrations."""
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config

    admin_url, db_name = _admin_url(TEST_DB_URL)

    sync_admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with sync_admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    sync_admin.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    # Alembic env reads the URL via app settings, which we've already pointed at TEST_DB_URL
    command.upgrade(cfg, "head")

    yield

    # Best-effort teardown
    sync_admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with sync_admin.connect() as conn:
        conn.execute(
            sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{db_name}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    sync_admin.dispose()


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """Wipe user-data tables between tests. audit_log is append-only at the
    DB level; we use TRUNCATE which bypasses our row-level trigger, so tests
    can still reset state. (The trigger blocks DELETE, not TRUNCATE.)"""
    yield
    async with db_engine.begin() as conn:
        for table in (
            RefreshToken.__tablename__,
            Passkey.__tablename__,
            BrokerAccount.__tablename__,
            AuditLog.__tablename__,
            User.__tablename__,
        ):
            await conn.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))


@pytest_asyncio.fixture
async def app():
    a = create_app()
    # Rate limiter would otherwise carry state across tests via Redis and trip 429s.
    a.state.limiter.enabled = False
    return a


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def owner_user(db_session: AsyncSession) -> User:
    from app.db.models import UserRole

    user = User(
        email="owner@example.com",
        display_name="Test Owner",
        role=UserRole.OWNER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
