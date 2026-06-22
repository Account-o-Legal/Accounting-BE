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
from app.modules.reporting.services import generate_balance_sheet

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

        await void_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry_id=posted.id,
            reversal_date=date(2026, 1, 10),
            reason="Mistaken invoice",
        )

        balance_sheet = await generate_balance_sheet(
            db,
            tenant_id=TENANT_ID,
        )

        assert balance_sheet["total_assets"] == 0
        assert balance_sheet["total_liabilities"] == 0
        assert balance_sheet["total_equity"] == 0

        assert (
            balance_sheet["total_assets"]
            ==
            balance_sheet["total_liabilities"]
            + balance_sheet["total_equity"]
        )


def test_balance_sheet_voided_entry() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_balance_sheet_voided_entry()
    print("ok")