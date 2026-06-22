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
        name="Revenue",
        type="revenue",
    )

    expense = Account(
        tenant_id=TENANT_ID,
        code="5000",
        name="Rent Expense",
        type="expense",
    )

    db.add(cash)
    db.add(revenue)
    db.add(expense)

    await db.flush()

    ids = {
        "cash": cash.id,
        "revenue": revenue.id,
        "expense": expense.id,
    }

    await db.commit()

    return ids


async def _post_revenue(
    db: AsyncSession,
    *,
    cash_id: str,
    revenue_id: str,
    entry_date: date,
    amount: float,
) -> None:
    await post_journal_entry(
        db,
        tenant_id=TENANT_ID,
        actor_user_id=ACTOR_ID,
        entry=JournalEntry(
            tenant_id=TENANT_ID,
            entry_date=entry_date,
            memo="Revenue",
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


async def _post_expense(
    db: AsyncSession,
    *,
    cash_id: str,
    expense_id: str,
    entry_date: date,
    amount: float,
) -> None:
    await post_journal_entry(
        db,
        tenant_id=TENANT_ID,
        actor_user_id=ACTOR_ID,
        entry=JournalEntry(
            tenant_id=TENANT_ID,
            entry_date=entry_date,
            memo="Expense",
        ),
        lines=[
            JournalLine(
                account_id=expense_id,
                debit=amount,
                credit=0,
            ),
            JournalLine(
                account_id=cash_id,
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

        await _post_revenue(
            db,
            cash_id=accounts["cash"],
            revenue_id=accounts["revenue"],
            entry_date=date(2026, 1, 10),
            amount=1000,
        )

        await _post_revenue(
            db,
            cash_id=accounts["cash"],
            revenue_id=accounts["revenue"],
            entry_date=date(2026, 2, 10),
            amount=500,
        )

        await _post_expense(
            db,
            cash_id=accounts["cash"],
            expense_id=accounts["expense"],
            entry_date=date(2026, 2, 15),
            amount=200,
        )

        pnl = await generate_profit_and_loss(
            db,
            tenant_id=TENANT_ID,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )

        assert pnl["total_revenue"] == 500
        assert pnl["total_expenses"] == 200
        assert pnl["net_income"] == 300


def test_profit_and_loss_date_range() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_profit_and_loss_date_range()
    print("ok")