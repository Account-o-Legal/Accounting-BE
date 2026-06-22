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

TENANT_ID = "tenant-a"
ACTOR_ID = "user-a"


async def _seed_accounts(db: AsyncSession) -> dict[str, str]:
    cash = Account(
        tenant_id=TENANT_ID,
        code="1000",
        name="Cash",
        type="asset",
    )

    revenue = Account(
        tenant_id=TENANT_ID,
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


async def _post(
    db: AsyncSession,
    *,
    entry_date: date,
    cash_id: str,
    revenue_id: str,
    amount: float,
) -> None:
    await post_journal_entry(
        db,
        tenant_id=TENANT_ID,
        actor_user_id=ACTOR_ID,
        entry=JournalEntry(
            tenant_id=TENANT_ID,
            entry_date=entry_date,
            memo=f"Revenue {amount}",
        ),
        lines=[
            JournalLine(
                account_id=cash_id,
                debit=amount,
                credit=0,
            ),
            JournalLine(
                account_id=revenue_id,
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
        accounts = await _seed_accounts(db)

        await _post(
            db,
            entry_date=date(2026, 1, 15),
            cash_id=accounts["cash"],
            revenue_id=accounts["revenue"],
            amount=1000,
        )

        await _post(
            db,
            entry_date=date(2026, 2, 15),
            cash_id=accounts["cash"],
            revenue_id=accounts["revenue"],
            amount=500,
        )

        tb = await generate_trial_balance(
            db,
            tenant_id=TENANT_ID,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )

        assert tb["total_debit"] == 500
        assert tb["total_credit"] == 500
        assert tb["is_balanced"] is True


def test_trial_balance_date_range() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_trial_balance_date_range()
    print("ok")