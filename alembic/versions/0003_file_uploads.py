"""add file_uploads table

ponytail: hand-written, same caveat as 0001_initial and 0002_vendor_rules
— not run against a live DB by me. Run `alembic upgrade head` yourself
and confirm it applies cleanly before trusting it.

Revision ID: 0003_file_uploads
Revises: 0002_vendor_rules
Create Date: 2026-06-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_file_uploads"
down_revision = "0002_vendor_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_uploads",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("tenant_id", sa.String(26), nullable=False),
        sa.Column("original_filename", sa.String, nullable=False),
        sa.Column("quarantine_key", sa.String, nullable=False),
        sa.Column("final_key", sa.String, nullable=True),
        sa.Column("scan_status", sa.String, nullable=False, server_default="pending"),
        sa.Column("scan_message", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_file_uploads_tenant_id", "file_uploads", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("file_uploads")