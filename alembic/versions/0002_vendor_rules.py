"""add vendor_rules table

ponytail: VendorRule (app/modules/banking/rules.py) was added to the
codebase after 0001_initial.py was written and never got its own
migration — the import worker's _load_vendor_rules() query was failing
with UndefinedTableError because the table genuinely never existed.
This is a pure addition, no changes to existing tables.

Revision ID: 0002_vendor_rules
Revises: 0001_initial
Create Date: 2026-06-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_vendor_rules"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendor_rules",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("tenant_id", sa.String(26), nullable=False),
        sa.Column("vendor_pattern", sa.String, nullable=False),
        sa.Column("account_id", sa.String(26), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vendor_rules_tenant_id", "vendor_rules", ["tenant_id"])
    op.create_index("ix_vendor_rules_vendor_pattern", "vendor_rules", ["vendor_pattern"])


def downgrade() -> None:
    op.drop_table("vendor_rules")