"""Append-only audit trail.

Lives in core/, not tax/ — every module that mutates state needs this
(ledger postings, invoice edits, bank reconciliation), not just tax. The
DB role for this table is INSERT-only at the Postgres grant level (see
infra/k8s migration job + GRANT statements in alembic), not just enforced
in application code.
"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, select
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


async def list_audit_events(
    db: AsyncSession,
    *,
    tenant_id: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 100,
) -> list[AuditLogEntry]:
    """Read side of the audit trail — exists now that something actually
    needs to view it (the audit router), not just write to it. An audit
    log nobody can read is only half a trust feature.

    ponytail: limit defaults to 100 and is the only pagination mechanism
    right now — no cursor-based paging (see core/pagination.py, unused
    here). Fine for an MVP where a single client's audit history is in
    the hundreds, not millions, of rows; revisit with real pagination if
    a workspace's event count ever makes "most recent 100" insufficient.
    """
    query = select(AuditLogEntry).where(AuditLogEntry.tenant_id == tenant_id)
    if entity_type is not None:
        query = query.where(AuditLogEntry.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditLogEntry.entity_id == entity_id)
    query = query.order_by(AuditLogEntry.created_at.desc()).limit(limit)

    result = await db.exec(query)
    return list(result.all())