"""Seeds a brand-new workspace's Chart of Accounts and default tax rates
from its jurisdiction pack. Without this, a freshly created workspace has
zero Account rows and zero TaxRate rows — AI categorization has nothing to
suggest against, approve_transaction has nothing to point at, and invoice
GST lines silently produce a ValidationError when a caller supplies a
tax_rate_id that doesn't exist yet.

Both functions are called once, atomically, at workspace creation
(see auth/router.py register()).
"""

from app.core.config import load_jurisdiction
from app.modules.accounting_core.models import Account
from app.modules.tax.models import TaxRate
from sqlmodel.ext.asyncio.session import AsyncSession


async def seed_chart_of_accounts(
    db: AsyncSession, *, tenant_id: str, jurisdiction_code: str
) -> list[Account]:
    pack = load_jurisdiction(jurisdiction_code)
    accounts = [
        Account(
            tenant_id=tenant_id,
            code=entry["code"],
            name=entry["name"],
            type=entry["type"],
        )
        for entry in pack["default_chart_of_accounts"]
    ]
    for account in accounts:
        db.add(account)
    await db.flush()  # ponytail: caller commits — seeding must be atomic
    # with workspace creation, not a separate transaction that could leave
    # a workspace with no accounts if it fails partway.
    return accounts


async def seed_tax_rates(
    db: AsyncSession, *, tenant_id: str, jurisdiction_code: str
) -> list[TaxRate]:
    """Seeds the jurisdiction's default tax rates. For PK this gives the
    workspace GST 17% and GST 0% (Exempt) immediately at registration so
    invoice lines can reference a real tax_rate_id without manual setup.

    ponytail: called in the same db.flush()/db.commit() cycle as
    seed_chart_of_accounts so all seeding is one atomic transaction — a
    workspace either has everything or nothing, never a partial seed.
    """
    pack = load_jurisdiction(jurisdiction_code)
    rates = [
        TaxRate(
            tenant_id=tenant_id,
            name=entry["name"],
            rate_percent=entry["rate_percent"],
            is_default=entry.get("is_default", False),
        )
        for entry in pack.get("default_tax_rates", [])
    ]
    for rate in rates:
        db.add(rate)
    await db.flush()
    return rates


def find_account_by_code(accounts: list[Account], code: str) -> Account | None:
    """Convenience lookup, e.g. find_account_by_code(accounts, '1020') to
    get the default 'Bank Account' ledger row right after seeding, so the
    caller can immediately create a matching BankAccount."""
    return next((a for a in accounts if a.code == code), None)