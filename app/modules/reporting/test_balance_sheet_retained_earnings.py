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


async def _post_owner_capital(
    db: AsyncSession,
    *,
    cash_id: str,
    equity_id: str,
) -> None:
    await post_journal_entry(
        db,
        tenant_id=TENANT_ID,
        actor_user_id=ACTOR_ID,
        entry=JournalEntry(
            tenant_id=TENANT_ID,
            entry_date=date(2026, 1, 1),
            memo="Owner investment",
        ),
        lines=[
            JournalLine(
                account_id=cash_id,
                debit=1000,
                credit=0,
            ),
            JournalLine(
                account_id=equity_id,
                debit=0,
                credit=1000,
            ),
        ],
    )


async def _post_revenue(
    db: AsyncSession,
    *,
    cash_id: str,
    revenue_id: str,
) -> None:
    await post_journal_entry(
        db,
        tenant_id=TENANT_ID,
        actor_user_id=ACTOR_ID,
        entry=JournalEntry(
            tenant_id=TENANT_ID,
            entry_date=date(2026, 1, 2),
            memo="Consulting income",
        ),
        lines=[
            JournalLine(
                account_id=cash_id,
                debit=500,
                credit=0,
            ),
            JournalLine(
                account_id=revenue_id,
                debit=0,
                credit=500,
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

        await _post_owner_capital(
            db,
            cash_id=accounts["cash"],
            equity_id=accounts["equity"],
        )

        await _post_revenue(
            db,
            cash_id=accounts["cash"],
            revenue_id=accounts["revenue"],
        )

        balance_sheet = await generate_balance_sheet(
            db,
            tenant_id=TENANT_ID,
        )

        assert round(balance_sheet["total_assets"], 2) == 1500.00

        assert round(balance_sheet["total_equity"], 2) == 1500.00, (
            "Retained earnings are not flowing into equity. "
            f"Expected 1500.00, got {balance_sheet['total_equity']}"
        )

        assert round(
            balance_sheet["total_assets"],
            2,
        ) == round(
            balance_sheet["total_liabilities"]
            + balance_sheet["total_equity"],
            2,
        )


def test_balance_sheet_retained_earnings() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_balance_sheet_retained_earnings()
    print("ok")