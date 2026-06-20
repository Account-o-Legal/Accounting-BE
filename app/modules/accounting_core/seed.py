"""Seeds a brand-new workspace's Chart of Accounts from its jurisdiction
pack. Without this, a freshly created workspace has zero Account rows,
which means AI categorization (ai/services.py) has nothing to suggest
against and approve_transaction has nothing to point at — this is the
gap that blocks the whole review-queue loop from working end to end.

Called once, at workspace creation (see auth/router.py register()).
"""

from app.core.config import load_jurisdiction
from app.modules.accounting_core.models import Account
from sqlmodel.ext.asyncio.session import AsyncSession


async def seed_chart_of_accounts(db: AsyncSession, *, tenant_id: str, jurisdiction_code: str) -> list[Account]:
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


def find_account_by_code(accounts: list[Account], code: str) -> Account | None:
    """Convenience lookup, e.g. find_account_by_code(accounts, '1020') to
    get the default 'Bank Account' ledger row right after seeding, so the
    caller can immediately create a matching BankAccount."""
    return next((a for a in accounts if a.code == code), None)