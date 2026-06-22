"""Report aggregation. Every function here reads POSTED and VOID journal
entries — never DRAFT (a real status, used for entries awaiting human
approval that have no business appearing in any report at all).

VOID entries are deliberately included, not excluded: a voided entry and
its reversal are both real postings that happened, and showing both
(rather than making the original silently vanish) is the standard an
auditor or FBR review expects — "this was recorded, then reversed" is
visible history, not erased history. Because a reversal is always the
exact mirror image of the entry it reverses (see
accounting_core/void.py), including both in the same aggregation
naturally nets every affected account back to its pre-error balance —
no special-case "void doesn't count" logic needed; it falls out of the
arithmetic for free.

This is the proof step for the whole ledger: if double-entry posting
(accounting_core/services.py) and transaction approval (banking/router.py)
are both correct, trial_balance() must always come back balanced. That
invariant is the test in test_trial_balance.py — not just "does this
return data" but "does debit always equal credit."
"""

from collections import defaultdict
from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.enums import JournalEntryStatus
from app.modules.accounting_core.models import Account, JournalEntry, JournalLine

# Account.type values that increase the books on the credit side.
# Used to compute a signed "balance" per account in the trial balance
# and to bucket accounts into P&L vs Balance Sheet sections.
_CREDIT_NORMAL_TYPES = {"liability", "equity", "revenue"}
_DEBIT_NORMAL_TYPES = {"asset", "expense"}

# Entries in these statuses are real, recorded history — DRAFT is the
# only status excluded (entries awaiting approval, never actually posted).
_REPORTABLE_STATUSES = (JournalEntryStatus.POSTED, JournalEntryStatus.VOID)


async def _posted_lines_with_accounts(
    db: AsyncSession,
    *,
    tenant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[tuple[JournalLine, Account]]:
    """Shared base query: every JournalLine belonging to a POSTED or VOID
    entry for this tenant, joined to its Account, optionally bounded by
    entry date. Every report function below is a different grouping of
    this same result set — kept as one query helper so "which statuses
    count" can't drift between reports.
    """
    query = (
        select(JournalLine, Account)
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .join(Account, JournalLine.account_id == Account.id)
        .where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.status.in_(_REPORTABLE_STATUSES),
        )
    )
    if start_date is not None:
        query = query.where(JournalEntry.entry_date >= start_date)
    if end_date is not None:
        query = query.where(JournalEntry.entry_date <= end_date)

    result = await db.exec(query)
    return list(result.all())


async def generate_trial_balance(db: AsyncSession, *, tenant_id: str) -> dict:
    """Every account with posted activity, its total debits/credits, and
    a signed balance. The ledger is only correct if
    sum(all account balances, debit-normal positive / credit-normal
    negative) nets to zero — that's what test_trial_balance.py checks.
    """
    rows = await _posted_lines_with_accounts(db, tenant_id=tenant_id)

    totals: dict[str, dict] = {}
    for line, account in rows:
        bucket = totals.setdefault(
            account.id,
            {
                "account_id": account.id,
                "code": account.code,
                "name": account.name,
                "type": account.type,
                "debit": 0.0,
                "credit": 0.0,
            },
        )
        bucket["debit"] += line.debit
        bucket["credit"] += line.credit

    accounts = sorted(totals.values(), key=lambda a: a["code"])
    for account in accounts:
        account["balance"] = round(account["debit"] - account["credit"], 2)

    total_debit = round(sum(a["debit"] for a in accounts), 2)
    total_credit = round(sum(a["credit"] for a in accounts), 2)

    return {
        "tenant_id": tenant_id,
        "accounts": accounts,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": total_debit == total_credit,
    }


async def generate_profit_and_loss(
    db: AsyncSession,
    *,
    tenant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Revenue and expense accounts only, for an optional date range.
    revenue is credit-normal (credit - debit); expense is debit-normal
    (debit - credit). net_income = revenue - expenses.
    """
    rows = await _posted_lines_with_accounts(
        db, tenant_id=tenant_id, start_date=start_date, end_date=end_date
    )

    revenue_by_account: dict[str, float] = defaultdict(float)
    expense_by_account: dict[str, float] = defaultdict(float)
    account_names: dict[str, str] = {}

    for line, account in rows:
        account_names[account.id] = account.name
        if account.type == "revenue":
            revenue_by_account[account.id] += line.credit - line.debit
        elif account.type == "expense":
            expense_by_account[account.id] += line.debit - line.credit

    revenue_lines = [
        {"account_id": acc_id, "name": account_names[acc_id], "amount": round(amt, 2)}
        for acc_id, amt in revenue_by_account.items()
    ]
    expense_lines = [
        {"account_id": acc_id, "name": account_names[acc_id], "amount": round(amt, 2)}
        for acc_id, amt in expense_by_account.items()
    ]

    total_revenue = round(sum(revenue_by_account.values()), 2)
    total_expenses = round(sum(expense_by_account.values()), 2)

    return {
        "tenant_id": tenant_id,
        "start_date": start_date,
        "end_date": end_date,
        "revenue": revenue_lines,
        "expenses": expense_lines,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_income": round(total_revenue - total_expenses, 2),
    }


async def generate_balance_sheet(db: AsyncSession, *, tenant_id: str, as_of: date | None = None) -> dict:
    """Asset, liability, and equity accounts, as of a point in time
    (defaults to all posted activity to date — no end_date filter means
    "everything up to now").

    Folds current-period net income (revenue - expenses) into equity as
    a synthetic "Retained Earnings (current period)" line. This is the
    standard treatment for books with no formal period-close yet: real
    accounting systems move net income into a retained earnings equity
    account at period close, but accounting_periods.is_closed isn't
    enforced in this codebase yet (see AccountingPeriod model). Until it
    is, computing it at report time is the only way assets == liabilities
    + equity actually ties out — without this line, equity would always
    be understated by exactly net_income, and the balance sheet would
    silently look "almost right" instead of correct.

    ponytail: once period-close is built, this should switch to summing
    an actual retained_earnings ledger account that period-close postings
    write to, rather than recomputing P&L at report time — that's the
    "real" implementation; this is the correct interim one.
    """
    rows = await _posted_lines_with_accounts(db, tenant_id=tenant_id, end_date=as_of)

    asset_by_account: dict[str, float] = defaultdict(float)
    liability_by_account: dict[str, float] = defaultdict(float)
    equity_by_account: dict[str, float] = defaultdict(float)
    account_names: dict[str, str] = {}

    total_revenue = 0.0
    total_expenses = 0.0

    for line, account in rows:
        account_names[account.id] = account.name
        if account.type == "asset":
            asset_by_account[account.id] += line.debit - line.credit
        elif account.type == "liability":
            liability_by_account[account.id] += line.credit - line.debit
        elif account.type == "equity":
            equity_by_account[account.id] += line.credit - line.debit
        elif account.type == "revenue":
            total_revenue += line.credit - line.debit
        elif account.type == "expense":
            total_expenses += line.debit - line.credit

    def _as_lines(by_account: dict[str, float]) -> list[dict]:
        return [
            {"account_id": acc_id, "name": account_names[acc_id], "amount": round(amt, 2)}
            for acc_id, amt in by_account.items()
        ]

    equity_lines = _as_lines(equity_by_account)
    current_period_net_income = round(total_revenue - total_expenses, 2)
    if current_period_net_income != 0:
        equity_lines.append(
            {
                "account_id": None,
                "name": "Retained Earnings (current period)",
                "amount": current_period_net_income,
            }
        )

    total_equity = round(sum(equity_by_account.values()) + current_period_net_income, 2)

    return {
        "tenant_id": tenant_id,
        "as_of": as_of,
        "assets": _as_lines(asset_by_account),
        "liabilities": _as_lines(liability_by_account),
        "equity": equity_lines,
        "total_assets": round(sum(asset_by_account.values()), 2),
        "total_liabilities": round(sum(liability_by_account.values()), 2),
        "total_equity": total_equity,
    }