"""Append-only audit trail.

Lives in core/, not tax/ — every module that mutates state needs this
(ledger postings, invoice edits, bank reconciliation), not just tax. The
DB role for this table is INSERT-only at the Postgres grant level (see
infra/k8s migration job + GRANT statements in alembic), not just enforced
in application code.
"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.mixins import TenantMixin, ULIDMixin


class AuditLogEntry(ULIDMixin, TenantMixin, SQLModel, table=True):
    __tablename__ = "audit_log_entries"

    actor_user_id: str = Field(index=True)
    entity_type: str = Field(index=True)  # "journal_entry", "invoice"...
    entity_id: str = Field(index=True)
    action: str  # "create", "update", "void"
    diff_json: str  # serialized before/after, no raw PII dumped
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


async def record_audit_event(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    diff_json: str,
) -> None:
    db.add(
        AuditLogEntry(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            diff_json=diff_json,
        )
    )
    # ponytail: caller's existing transaction commits this — no separate
    # commit here, audit write must be atomic with the business mutation
    # it's recording, not a fire-and-forget afterthought.
