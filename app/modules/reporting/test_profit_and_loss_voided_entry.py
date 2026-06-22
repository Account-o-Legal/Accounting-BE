# app/modules/reporting/test_profit_and_loss_voided_entry.py

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
from app.modules.accounting_core.void import void_journal_entry
from app.modules.reporting.services import generate_profit_and_loss

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
        name="Service Revenue",
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


async def _run() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as db:
        accounts = await _seed_accounts(db)

        posted = await post_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry=JournalEntry(
                tenant_id=TENANT_ID,
                entry_date=date(2026, 1, 10),
                memo="Revenue to be voided",
            ),
            lines=[
                JournalLine(
                    account_id=accounts["cash"],
                    debit=1000,
                    credit=0,
                ),
                JournalLine(
                    account_id=accounts["revenue"],
                    debit=0,
                    credit=1000,
                ),
            ],
        )

        posted_id = posted.id

        await void_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry_id=posted_id,
            reversal_date=date(2026, 1, 10),
            reason="Mistaken invoice",
        )

        pnl = await generate_profit_and_loss(
            db,
            tenant_id=TENANT_ID,
        )

        assert pnl["total_revenue"] == 0
        assert pnl["net_income"] == 0


def test_profit_and_loss_voided_entry() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_profit_and_loss_voided_entry()
    print("ok")