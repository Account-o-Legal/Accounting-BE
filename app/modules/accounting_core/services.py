"""The single most important function in the codebase: post_journal_entry.
Everything else (invoices, bills, bank reconciliation, AI suggestions)
eventually calls this. If this function has a bug, the books are wrong.

ponytail: balance check is a plain sum() in Python over already-loaded
lines, not a DB-level CHECK constraint. A DB constraint can't easily
express "debits == credits across a dynamic set of rows" without a
trigger; a trigger is the "right" long-term answer but is also the kind
of thing you write once you have one (the period-close trigger), not
speculatively now. The Python check + this comment is the interim truth.
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.audit import record_audit_event
from app.core.enums import JournalEntryStatus
from app.core.exceptions import UnbalancedEntryError
from app.modules.accounting_core.models import JournalEntry, JournalLine
from app.observability.otel import journal_entries_posted
from app.modules.accounting_core.periods import ensure_period_open

async def post_journal_entry(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str,
    entry: JournalEntry,
    lines: list[JournalLine],
) -> JournalEntry:
    total_debit = sum(line.debit for line in lines)
    total_credit = sum(line.credit for line in lines)
    if round(total_debit - total_credit, 2) != 0:
        raise UnbalancedEntryError(
            f"Entry does not balance: debit={total_debit} credit={total_credit}"
        )
    await ensure_period_open(
        db,
        tenant_id=tenant_id,
        entry_date=entry.entry_date,
    )
    entry.tenant_id = tenant_id
    entry.status = JournalEntryStatus.POSTED
    db.add(entry)
    await db.flush()
    for line in lines:
        line.journal_entry_id = entry.id
        db.add(line)

    await record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="journal_entry",
        entity_id=entry.id,
        action="post",
        diff_json=f'{{"debit": {total_debit}, "credit": {total_credit}}}',
    )
    journal_entries_posted.add(1, {"source": entry.source})
    await db.commit()
    return entry
