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

    equity = Account(
        tenant_id=TENANT_ID,
        code="3000",
        name="Owner Equity",
        type="equity",
    )

    db.add(cash)
    db.add(revenue)
    db.add(equity)

    await db.flush()

    ids = {
        "cash": cash.id,
        "revenue": revenue.id,
        "equity": equity.id,
    }

    await db.commit()

    return ids


async def _post_entry(
    db: AsyncSession,
    *,
    entry_date: date,
    debit_account_id: str,
    credit_account_id: str,
    amount: float,
    memo: str,
) -> None:
    await post_journal_entry(
        db,
        tenant_id=TENANT_ID,
        actor_user_id=ACTOR_ID,
        entry=JournalEntry(
            tenant_id=TENANT_ID,
            entry_date=entry_date,
            memo=memo,
        ),
        lines=[
            JournalLine(
                account_id=debit_account_id,
                debit=amount,
                credit=0,
            ),
            JournalLine(
                account_id=credit_account_id,
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

    async with AsyncSession(engine) as db:
        accounts = await _seed_accounts(db)

        # January owner investment
        await _post_entry(
            db,
            entry_date=date(2026, 1, 1),
            debit_account_id=accounts["cash"],
            credit_account_id=accounts["equity"],
            amount=1000,
            memo="Owner investment",
        )

        # January revenue
        await _post_entry(
            db,
            entry_date=date(2026, 1, 15),
            debit_account_id=accounts["cash"],
            credit_account_id=accounts["revenue"],
            amount=500,
            memo="January consulting income",
        )

        # February revenue (must NOT appear in Jan 31 balance sheet)
        await _post_entry(
            db,
            entry_date=date(2026, 2, 15),
            debit_account_id=accounts["cash"],
            credit_account_id=accounts["revenue"],
            amount=700,
            memo="February consulting income",
        )

        balance_sheet = await generate_balance_sheet(
            db,
            tenant_id=TENANT_ID,
            as_of_date=date(2026, 1, 31),
        )

        assert round(balance_sheet["total_assets"], 2) == 1500.00, (
            "Future-dated transactions leaked into January balance sheet"
        )

        assert round(balance_sheet["total_equity"], 2) == 1500.00

        assert round(
            balance_sheet["total_assets"],
            2,
        ) == round(
            balance_sheet["total_liabilities"]
            + balance_sheet["total_equity"],
            2,
        )


def test_balance_sheet_as_of_date() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_balance_sheet_as_of_date()
    print("ok")