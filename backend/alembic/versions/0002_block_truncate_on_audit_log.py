"""Block TRUNCATE on audit_log.

Postgres TRUNCATE bypasses row-level triggers, so the BEFORE UPDATE/DELETE
trigger from 0001_initial is not enough — a malicious or careless TRUNCATE
would silently wipe the audit trail. This migration adds a STATEMENT-LEVEL
BEFORE TRUNCATE trigger that calls a dedicated function and raises.

Revision ID: 0002_block_truncate
Revises: 0001_initial
Create Date: 2026-04-30 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_block_truncate"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Statement-level trigger function for TRUNCATE. Cannot reuse the row-level
    # function from 0001 because TG_OP context differs and we want a clear
    # message that names TRUNCATE explicitly.
    # exec_driver_sql + %% to bypass psycopg2 paramstyle escaping (see Phase 1 fix #2).
    op.get_bind().exec_driver_sql(
        """
        CREATE OR REPLACE FUNCTION audit_log_block_truncate() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only (operation TRUNCATE denied)';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_block_truncate();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_truncate();")
