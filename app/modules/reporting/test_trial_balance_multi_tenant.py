import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import (
    Account,
    JournalEntry,
    JournalLine,
)
from app.modules.accounting_core.services import post_journal_entry
from app.modules.reporting.services import generate_trial_balance

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
ACTOR_ID = "user-a"


async def _seed_accounts(
    db: AsyncSession,
    *,
    tenant_id: str,
) -> dict[str, str]:
    cash = Account(
        tenant_id=tenant_id,
        code="1000",
        name="Cash",
        type="asset",
    )

    revenue = Account(
        tenant_id=tenant_id,
        code="4000",
        name="Revenue",
        type="revenue",
    )

    db.add(cash)
    db.add(revenue)

    await db.flush()

    ids = {
        "cash": cash.id,
        "revenue": revenue.id,
    }

    await db.commit()

    return ids


async def _post_revenue(
    db: AsyncSession,
    *,
    tenant_id: str,
    amount: float,
    accounts: dict[str, str],
) -> None:
    await post_journal_entry(
        db,
        tenant_id=tenant_id,
        actor_user_id=ACTOR_ID,
        entry=JournalEntry(
            tenant_id=tenant_id,
            entry_date=date(2026, 1, 10),
            memo="Revenue",
        ),
        lines=[
            JournalLine(
                account_id=accounts["cash"],
                debit=amount,
                credit=0,
            ),
            JournalLine(
                account_id=accounts["revenue"],
                debit=0,
                credit=amount,
            ),
        ],
    )


async def _run() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as db:
        tenant_a_accounts = await _seed_accounts(
            db,
            tenant_id=TENANT_A,
        )

        tenant_b_accounts = await _seed_accounts(
            db,
            tenant_id=TENANT_B,
        )

        await _post_revenue(
            db,
            tenant_id=TENANT_A,
            amount=1000,
            accounts=tenant_a_accounts,
        )

        await _post_revenue(
            db,
            tenant_id=TENANT_B,
            amount=5000,
            accounts=tenant_b_accounts,
        )

        tb = await generate_trial_balance(
            db,
            tenant_id=TENANT_A,
        )

        assert tb["total_debit"] == 1000
        assert tb["total_credit"] == 1000
        assert tb["is_balanced"] is True
        assert len(tb["accounts"]) == 2


def test_trial_balance_multi_tenant() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_trial_balance_multi_tenant()
    print("ok")