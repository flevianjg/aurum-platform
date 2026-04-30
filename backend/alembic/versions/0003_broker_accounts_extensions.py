"""Phase 2: extend broker_accounts with test/health metadata, add broker_health_checks.

Adds nullable columns to broker_accounts (so existing rows don't need backfill)
and a new broker_health_checks table that records every connection probe.

Revision ID: 0003_broker_ext
Revises: 0002_block_truncate
Create Date: 2026-04-30 05:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_broker_ext"
down_revision: str | None = "0002_block_truncate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "broker_accounts",
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "broker_accounts",
        sa.Column("last_test_status", sa.Text(), nullable=True),
    )
    op.add_column(
        "broker_accounts",
        sa.Column("last_test_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "broker_accounts",
        sa.Column("account_currency", sa.Text(), nullable=True),
    )
    op.add_column("broker_accounts", sa.Column("server", sa.Text(), nullable=True))
    op.add_column(
        "broker_accounts", sa.Column("account_number", sa.Text(), nullable=True)
    )
    op.add_column(
        "broker_accounts",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "broker_health_checks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "broker_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_broker_health_acct_ts",
        "broker_health_checks",
        ["broker_account_id", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_broker_health_acct_ts", table_name="broker_health_checks")
    op.drop_table("broker_health_checks")

    op.drop_column("broker_accounts", "deactivated_at")
    op.drop_column("broker_accounts", "account_number")
    op.drop_column("broker_accounts", "server")
    op.drop_column("broker_accounts", "account_currency")
    op.drop_column("broker_accounts", "last_test_error")
    op.drop_column("broker_accounts", "last_test_status")
    op.drop_column("broker_accounts", "last_tested_at")
