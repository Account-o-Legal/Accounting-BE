"""Accounts + journal entries — the ledger surface other modules' routers
either call into directly (banking/router.py's approve_transaction builds
JournalEntry/JournalLine objects itself) or could call via this router's
POST /journal-entries for manual entries.

ponytail: this is the minimum surface to unblock the API from crashing on
import (main.py expects accounting_core.router to exist) and to let a
human create a manual journal entry from the UI.
"""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from app.core.exceptions import NotFoundError
from app.dependencies import ActiveWorkspace, AdminWorkspace, CurrentUser, DbSession
from app.modules.accounting_core.models import (
    Account,
    AccountingPeriod,
    JournalEntry,
    JournalEntryCreate,
    JournalLine,
)
from app.modules.accounting_core.services import post_journal_entry
from app.modules.accounting_core.void import void_journal_entry

router = APIRouter()


class VoidJournalEntryRequest(BaseModel):
    # ponytail: explicit opt-in, not a silent default — see
    # void_journal_entry's docstring for why backdating a reversal is a
    # real compliance hazard, not just a style preference.
    reversal_date: date | None = None
    reason: str | None = None


@router.get("/accounts")
async def list_accounts(workspace: ActiveWorkspace, db: DbSession):
    """The Chart of Accounts for this client workspace — seeded at
    registration (see accounting_core/seed.py), editable here as the
    workspace's needs grow."""
    rows = await db.exec(select(Account).where(Account.tenant_id == workspace))
    return rows.all()


@router.post("/journal-entries")
async def create_journal_entry(
    body: JournalEntryCreate, workspace: ActiveWorkspace, user: CurrentUser, db: DbSession
):
    """Manual journal entry. The AI-suggested / bank-import path posts
    through this same post_journal_entry() service directly from
    banking/router.py's approve_transaction — this endpoint exists for
    the human-entered case (a correction, an entry with no bank
    transaction behind it, etc.)."""
    entry = JournalEntry(
        tenant_id=workspace,
        entry_date=body.entry_date,
        memo=body.memo,
        source="manual",
    )
    lines = [
        JournalLine(account_id=line.account_id, debit=line.debit, credit=line.credit)
        for line in body.lines
    ]
    posted = await post_journal_entry(
        db,
        tenant_id=workspace,
        actor_user_id=user["sub"],
        entry=entry,
        lines=lines,
    )
    return {"id": posted.id, "status": posted.status}


@router.get("/journal-entries/{entry_id}")
async def get_journal_entry(entry_id: str, workspace: ActiveWorkspace, db: DbSession):
    entry = (
        await db.exec(
            select(JournalEntry).where(
                JournalEntry.id == entry_id, JournalEntry.tenant_id == workspace
            )
        )
    ).first()
    if not entry:
        raise NotFoundError("Journal entry not found")

    lines = (
        await db.exec(
            select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
        )
    ).all()
    return {"entry": entry, "lines": lines}


@router.post("/journal-entries/{entry_id}/void")
async def void_entry(
    entry_id: str,
    workspace: AdminWorkspace,
    user: CurrentUser,
    db: DbSession,
    body: VoidJournalEntryRequest = VoidJournalEntryRequest(),
):
    """Owner/admin only (see AdminWorkspace / require_workspace_admin)
    — voiding affects the ledger and historical reports, not something
    a bookkeeper or viewer role should be able to trigger unsupervised.

    Never deletes or mutates the original entry: marks it VOID and posts
    a separate reversing entry. See void_journal_entry's docstring for
    the reasoning behind the date default.
    """
    voided = await void_journal_entry(
        db,
        tenant_id=workspace,
        actor_user_id=user["sub"],
        entry_id=entry_id,
        reversal_date=body.reversal_date,
        reason=body.reason,
    )
    return {"id": voided.id, "status": voided.status}


@router.get("/periods")
async def list_periods(workspace: ActiveWorkspace, db: DbSession):
    rows = await db.exec(
        select(AccountingPeriod).where(AccountingPeriod.tenant_id == workspace)
    )
    return rows.all()