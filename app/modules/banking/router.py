"""The review-queue endpoints — the one-tap approve/reject UX that's the
MVP's UX differentiator. Import itself is async (see workers/import_worker.py);
this router exposes the queue the AI populates and the human clears.
"""

from datetime import date

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel
from sqlmodel import select

from app.core.exceptions import NotFoundError, ValidationError
from app.dependencies import ActiveWorkspace, CurrentUser, DbSession
from app.modules.accounting_core.models import JournalEntry, JournalLine
from app.modules.accounting_core.services import post_journal_entry
from app.modules.banking.models import BankAccount, BankTransaction
from app.modules.banking.rules import VendorRule

router = APIRouter()


class ApproveTransactionRequest(BaseModel):
    # Optional: required when the transaction has no suggested_account_id
    # (a true rule-miss sitting in needs_review). When the AI already
    # suggested an account, the human can approve with no body at all —
    # this field lets them override that suggestion instead, if they want.
    account_id: str | None = None


@router.post("/import")
async def import_statement(file: UploadFile, workspace: ActiveWorkspace):
    """Enqueues the file for async processing — never parses inline on the
    request thread. See workers/import_worker.py for the categorization
    pipeline (rules first, LLM fallback second)."""
    from app.workers.main import import_queue  # ponytail: lazy import avoids worker startup cost on every API boot

    # ponytail: arq's enqueue_job() returns a Job object, not a plain id —
    # the response body needs the string .job_id, not the Job itself
    # (FastAPI's jsonable_encoder can't serialize an arq Job: it's neither
    # iterable nor a plain dataclass with __dict__).
    job = await import_queue.enqueue_job(
        "process_bank_statement", workspace, await file.read()
    )
    return {"job_id": job.job_id, "status": "queued"}


@router.get("/review-queue")
async def get_review_queue(workspace: ActiveWorkspace, db: DbSession):
    """Transactions awaiting human approval, AI-suggested-first so the
    accountant clears the easy ones fast."""
    rows = await db.exec(
        select(BankTransaction)
        .where(
            BankTransaction.tenant_id == workspace,
            BankTransaction.category_status.in_(["ai_suggested", "needs_review"]),
        )
        .order_by(BankTransaction.category_status.desc())
    )
    return rows.all()


@router.post("/transactions/{txn_id}/approve")
async def approve_transaction(
    txn_id: str,
    workspace: ActiveWorkspace,
    user: CurrentUser,
    db: DbSession,
    body: ApproveTransactionRequest = ApproveTransactionRequest(),
):
    """One-tap approve: takes the AI's suggested_account_id (or a human-
    chosen account_id for true rule-misses), posts a 2-line journal entry
    (bank leg + categorized leg), and marks the transaction resolved. This
    single action is the show-stopper UX moment — everything upstream
    exists to make this tap feel safe.

    A positive amount (money in) debits the bank account and credits the
    categorized account (e.g. revenue). A negative amount (money out)
    does the reverse. This is the standard convention for bank-feed
    postings — verify against your jurisdiction's chart of accounts
    sign conventions before going live with real money.

    Learning loop: if this transaction was a genuine rule-miss
    (category_status == "needs_review", no rule existed for this vendor
    pattern), approving it creates a VendorRule from the transaction's
    description -> the chosen account, so the same vendor auto-categorizes
    next time. Only fires once per vendor pattern — re-approving a
    transaction that already matched an existing rule doesn't create a
    duplicate or conflicting one.
    """
    txn = (
        await db.exec(
            select(BankTransaction).where(
                BankTransaction.id == txn_id, BankTransaction.tenant_id == workspace
            )
        )
    ).first()
    if not txn:
        raise NotFoundError("Transaction not found")

    was_rule_miss = txn.category_status == "needs_review"
    account_id = body.account_id or txn.suggested_account_id
    if not account_id:
        raise ValidationError(
            "No account specified — pass account_id in the request body for "
            "transactions with no AI-suggested category"
        )

    bank_account = (
        await db.exec(
            select(BankAccount).where(
                BankAccount.id == txn.bank_account_id, BankAccount.tenant_id == workspace
            )
        )
    ).first()
    if not bank_account:
        raise NotFoundError("Bank account not found")

    amount = abs(txn.amount)
    is_inflow = txn.amount >= 0

    entry = JournalEntry(
        tenant_id=workspace,
        entry_date=txn.txn_date,
        memo=txn.description,
        source="ai_suggested" if txn.category_status == "ai_suggested" else "manual",
    )
    lines = [
        JournalLine(
            account_id=bank_account.ledger_account_id,
            debit=amount if is_inflow else 0,
            credit=0 if is_inflow else amount,
        ),
        JournalLine(
            account_id=account_id,
            debit=0 if is_inflow else amount,
            credit=amount if is_inflow else 0,
        ),
    ]

    posted = await post_journal_entry(
        db,
        tenant_id=workspace,
        actor_user_id=user["sub"],
        entry=entry,
        lines=lines,
    )

    txn.suggested_account_id = account_id
    txn.journal_entry_id = posted.id
    txn.category_status = "auto"  # resolved — no longer needs human review

    # Learning loop: a resolved rule-miss becomes tomorrow's auto-match.
    # vendor_pattern is the txn description lower-cased — the same shape
    # ai/services.py's try_rule_match() does substring matching against,
    # so a rule created here is immediately usable by the next import.
    if was_rule_miss:
        vendor_pattern = txn.description.strip().lower()
        existing_rule = (
            await db.exec(
                select(VendorRule).where(
                    VendorRule.tenant_id == workspace,
                    VendorRule.vendor_pattern == vendor_pattern,
                )
            )
        ).first()
        if not existing_rule:
            db.add(
                VendorRule(
                    tenant_id=workspace,
                    vendor_pattern=vendor_pattern,
                    account_id=account_id,
                )
            )

    db.add(txn)
    await db.commit()

    return {"journal_entry_id": posted.id, "status": "posted"}