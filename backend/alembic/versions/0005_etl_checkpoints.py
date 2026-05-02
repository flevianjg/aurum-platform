"""Phase 4 — etl_checkpoints (one row per ETL source).

Revision ID: 0005_etl_checkpoints
Revises: 0004_paper_events
Create Date: 2026-05-01 21:30:01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_etl_checkpoints"
down_revision: str | None = "0004_paper_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "etl_checkpoints",
        sa.Column("source", sa.Text(), primary_key=True),
        sa.Column("last_processed_file", sa.Text(), nullable=True),
        sa.Column("last_processed_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("etl_checkpoints")
