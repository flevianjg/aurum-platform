"""Phase 4 — paper_events table for aurum_2 journal ingestion.

`event_id` is the primary key. For pre-contract journal lines that lack one,
the ETL synthesizes a stable UUID5 from (source_file, source_line, ts, type)
and sets event_id_synthetic=true so analytics can distinguish them.

Revision ID: 0004_paper_events
Revises: 0003_broker_ext
Create Date: 2026-05-01 21:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_paper_events"
down_revision: str | None = "0003_broker_ext"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instrument", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("source_line", sa.BigInteger(), nullable=False),
        sa.Column(
            "event_id_synthetic",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_paper_events_ts", "paper_events", ["ts"])
    op.create_index("ix_paper_events_type_ts", "paper_events", ["event_type", "ts"])
    op.create_index(
        "ix_paper_events_instrument_ts", "paper_events", ["instrument", "ts"]
    )


def downgrade() -> None:
    op.drop_index("ix_paper_events_instrument_ts", table_name="paper_events")
    op.drop_index("ix_paper_events_type_ts", table_name="paper_events")
    op.drop_index("ix_paper_events_ts", table_name="paper_events")
    op.drop_table("paper_events")
