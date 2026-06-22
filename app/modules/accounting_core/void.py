"""Reversing a posted journal entry. The one rule that must never be
violated: a posted entry is NEVER deleted or mutated. Its lines, its
amounts, its audit trail — all permanent. "Undo" means posting a new
entry that nets the original to zero and marking the original VOID so
reports stop counting it. This is standard double-entry practice, not a
stylistic choice — an accounting system that lets posted history be
edited or deleted is not defensible to an auditor or FBR, full stop.

Kept in its own file rather than added to services.py: post_journal_entry
is the single most sensitive function in this codebase, and reversal is
sensitive in a different way (date-handling judgment calls, not just the
balance invariant) — separating them means a change to one can't
accidentally destabilize the other.
"""

from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.modules.accounting_core.periods import ensure_period_open
from app.core.audit import record_audit_event
from app.core.enums import JournalEntryStatus
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.accounting_core.models import JournalEntry, JournalLine
from app.modules.accounting_core.services import post_journal_entry


async def void_journal_entry(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str,
    entry_id: str,
    reversal_date: date | None = None,
    reason: str | None = None,
) -> JournalEntry:
    """Marks `entry_id` VOID and posts an offsetting reversing entry.

    reversal_date: defaults to today (the date the void happens), not
    the original entry's date. This matters for compliance — backdating
    a reversal into an already-reported period is itself a problem (FBR
    filings, client-facing reports already sent, etc.), so "today" is
    the safe default. Pass the original entry's date explicitly only
    when the mistake is caught same-period and there's a real reason to
    keep that period's net effect at zero (e.g. same-day fat-finger fix
    before anything downstream has consumed the entry). This is a
    deliberate override, not a silent default — callers must opt in.

    A voided entry can't itself be voided again (no double-reversal),
    and an already-void entry can't be voided (nothing to undo twice).
    """
    original = (
    (
        await db.execute(
            select(JournalEntry).where(
                JournalEntry.id == entry_id,
                JournalEntry.tenant_id == tenant_id,
            )
        )
    )
        .scalars()
        .first()
    )
    if not original:
        raise NotFoundError("Journal entry not found")
    if original.status != JournalEntryStatus.POSTED:
        raise ValidationError(
            f"Cannot void an entry with status '{original.status}' — only POSTED entries can be voided"
        )

    original_lines = (
    (
        await db.execute(
            select(JournalLine).where(
                JournalLine.journal_entry_id == entry_id
            )
        )
    )
        .scalars()
        .all()
    )
    if not original_lines:
        # Shouldn't be reachable given post_journal_entry's invariants,
        # but fail loudly rather than silently post an empty/no-op
        # reversal if it somehow is.
        raise ValidationError("Original entry has no lines — nothing to reverse")

    effective_date = reversal_date or date.today()

    await ensure_period_open(
        db,
        tenant_id=tenant_id,
        entry_date=effective_date,
    )

    reversal_lines = [
        JournalLine(account_id=line.account_id, debit=line.credit, credit=line.debit)
        for line in original_lines
    ]

    memo = f"Reversal of entry {original.id}"
    if reason:
        memo += f": {reason}"

    reversal_entry = JournalEntry(
        tenant_id=tenant_id,
        entry_date=effective_date,
        memo=memo,
        source="reversal",
    )

    posted_reversal = await post_journal_entry(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entry=reversal_entry,
        lines=reversal_lines,
    )
    # ponytail: post_journal_entry already commits internally — the
    # original.status flip below happens in a SEPARATE commit, after the
    # reversal is confirmed posted. This ordering is deliberate: if the
    # original mutation succeeded but flipping the original's status
    # failed for some reason, the worst outcome is a posted reversal
    # sitting alongside a still-POSTED original (a balance error a human
    # would immediately notice in the trial balance) — not a voided
    # original with NO offsetting reversal anywhere in the ledger (a
    # silent, undetected loss of a transaction). Fail toward "extra
    # entry that's visibly wrong" over "missing entry that's invisibly wrong."

    original.status = JournalEntryStatus.VOID
    db.add(original)

    await record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="journal_entry",
        entity_id=original.id,
        action="void",
        diff_json=f'{{"reversal_entry_id": "{posted_reversal.id}", "reason": "{reason or ""}"}}',
    )
    await db.commit()

    return original