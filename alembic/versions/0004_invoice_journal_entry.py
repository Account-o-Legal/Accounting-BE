"""add journal_entry_id to invoices

ponytail: hand-written, same caveat as every other migration in this
repo — run `alembic upgrade head` yourself and confirm it applies
cleanly. Pure additive column, nullable, no backfill needed since
existing invoices (if any) simply have no ledger posting yet.

Revision ID: 0004_invoice_journal_entry
Revises: 0003_file_uploads
Create Date: 2026-06-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_invoice_journal_entry"
down_revision = "0003_file_uploads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("journal_entry_id", sa.String(26), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "journal_entry_id")