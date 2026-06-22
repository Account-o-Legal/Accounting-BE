import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import Account, JournalEntry, JournalLine
from app.modules.accounting_core.services import post_journal_entry
from app.modules.accounting_core.void import void_journal_entry
from app.modules.reporting.services import generate_profit_and_loss

TENANT_ID = "tenant-a"
ACTOR_ID = "user-a"


async def _run():
    engine = create_async_engine("sqlite+aiosqlite://", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as db:
        cash = Account(tenant_id=TENANT_ID, code="1000", name="Cash", type="asset")
        revenue = Account(tenant_id=TENANT_ID, code="4000", name="Revenue", type="revenue")

        db.add(cash)
        db.add(revenue)
        await db.commit()

        posted = await post_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry=JournalEntry(
                tenant_id=TENANT_ID,
                entry_date=date(2026, 1, 10),
            ),
            lines=[
                JournalLine(account_id=cash.id, debit=1000, credit=0),
                JournalLine(account_id=revenue.id, debit=0, credit=1000),
            ],
        )

        await void_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry_id=posted.id,
            reversal_date=date(2026, 2, 5),
        )

        jan = await generate_profit_and_loss(
            db,
            tenant_id=TENANT_ID,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        feb = await generate_profit_and_loss(
            db,
            tenant_id=TENANT_ID,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )

        combined = await generate_profit_and_loss(
            db,
            tenant_id=TENANT_ID,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 28),
        )

        assert jan["net_income"] == 1000
        assert feb["net_income"] == -1000
        assert combined["net_income"] == 0


def test_profit_and_loss_cross_period_void():
    asyncio.run(_run())


if __name__ == "__main__":
    test_profit_and_loss_cross_period_void()
    print("ok")