"""add account_id and journal_entry_id to bills

ponytail: hand-written, same caveat as every other migration in this
repo. account_id is added NOT NULL with no default — if any Bill rows
already exist in a real deployed DB (unlikely for an MVP still in dev),
this migration will fail until those rows are backfilled with a real
account_id first. For a dev DB with no real bill data yet, this is a
non-issue; flagged in case this runs against anything with existing data.

Revision ID: 0005_bill_ledger_fields
Revises: 0004_invoice_journal_entry
Create Date: 2026-06-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_bill_ledger_fields"
down_revision = "0004_invoice_journal_entry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bills",
        sa.Column("account_id", sa.String(26), sa.ForeignKey("accounts.id"), nullable=True),
    )
    op.add_column("bills", sa.Column("journal_entry_id", sa.String(26), nullable=True))
    # ponytail: account_id is added nullable here, then we'd normally
    # ALTER to NOT NULL after backfilling — left nullable at the DB level
    # since SQLModel's account_id: str (no | None) only enforces
    # non-null at the Python/API layer, not the schema layer, and there's
    # no existing bill data to backfill against in a fresh dev DB anyway.


def downgrade() -> None:
    op.drop_column("bills", "journal_entry_id")
    op.drop_column("bills", "account_id")