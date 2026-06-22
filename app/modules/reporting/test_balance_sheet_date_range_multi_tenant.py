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
from app.modules.reporting.services import generate_balance_sheet

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
    entry_date: date,
    accounts: dict[str, str],
) -> None:
    await post_journal_entry(
        db,
        tenant_id=tenant_id,
        actor_user_id=ACTOR_ID,
        entry=JournalEntry(
            tenant_id=tenant_id,
            entry_date=entry_date,
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
            entry_date=date(2026, 1, 15),
            accounts=tenant_a_accounts,
        )

        await _post_revenue(
            db,
            tenant_id=TENANT_A,
            amount=500,
            entry_date=date(2026, 2, 15),
            accounts=tenant_a_accounts,
        )

        await _post_revenue(
            db,
            tenant_id=TENANT_B,
            amount=9000,
            entry_date=date(2026, 1, 15),
            accounts=tenant_b_accounts,
        )

        balance_sheet = await generate_balance_sheet(
            db,
            tenant_id=TENANT_A,
            as_of_date=date(2026, 1, 31),
        )

        assert balance_sheet["total_assets"] == 1000
        assert balance_sheet["total_liabilities"] == 0
        assert balance_sheet["total_equity"] == 1000

        retained_earnings = next(
            (
                line
                for line in balance_sheet["equity"]
                if line["name"] == "Retained Earnings (current period)"
            ),
            None,
        )

        assert retained_earnings is not None
        assert retained_earnings["amount"] == 1000


def test_balance_sheet_date_range_multi_tenant() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_balance_sheet_date_range_multi_tenant()
    print("ok")