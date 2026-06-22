import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import (
    Account,
    AccountingPeriod,
    JournalEntry,
    JournalLine,
)
from app.modules.accounting_core.services import post_journal_entry
from app.modules.accounting_core.periods import close_period
from app.modules.reporting.services import generate_balance_sheet

TENANT_ID = "tenant-a"
ACTOR_ID = "user-a"


async def _run():
    engine = create_async_engine("sqlite+aiosqlite://", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Add expire_on_commit=False to the session constructor here
    async with AsyncSession(engine, expire_on_commit=False) as db:
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

        period = AccountingPeriod(
            tenant_id=TENANT_ID,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_closed=False,
        )

        db.add(cash)
        db.add(revenue)
        db.add(period)

        await db.commit()

        # All model IDs are safely preserved and accessible now!
        await post_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry=JournalEntry(
                tenant_id=TENANT_ID,
                entry_date=date(2026, 6, 1),
            ),
            lines=[
                JournalLine(account_id=cash.id, debit=1000, credit=0),
                JournalLine(account_id=revenue.id, debit=0, credit=1000),
            ],
        )

        await close_period(
            db,
            tenant_id=TENANT_ID,
            period_id=period.id,
            actor_user_id=ACTOR_ID,  # Remember to keep the audit track parameter!
        )

        bs = await generate_balance_sheet(
            db,
            tenant_id=TENANT_ID,
        )

        assert bs["total_assets"] > 0

def test_retained_earnings_close():
    asyncio.run(_run())


if __name__ == "__main__":
    test_retained_earnings_close()
    print("ok")