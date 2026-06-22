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

    equity = Account(
        tenant_id=tenant_id,
        code="3000",
        name="Owner Equity",
        type="equity",
    )

    db.add(cash)
    db.add(equity)

    await db.flush()

    ids = {
        "cash": cash.id,
        "equity": equity.id,
    }

    await db.commit()

    return ids


async def _post_capital(
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
            entry_date=date(2026, 1, 1),
            memo="Owner investment",
        ),
        lines=[
            JournalLine(
                account_id=accounts["cash"],
                debit=amount,
                credit=0,
            ),
            JournalLine(
                account_id=accounts["equity"],
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

        await _post_capital(
            db,
            tenant_id=TENANT_A,
            amount=1000,
            accounts=tenant_a_accounts,
        )

        await _post_capital(
            db,
            tenant_id=TENANT_B,
            amount=9000,
            accounts=tenant_b_accounts,
        )

        balance_sheet = await generate_balance_sheet(
            db,
            tenant_id=TENANT_A,
        )

        assert balance_sheet["total_assets"] == 1000
        assert balance_sheet["total_equity"] == 1000
        assert balance_sheet["total_liabilities"] == 0


def test_balance_sheet_multi_tenant() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_balance_sheet_multi_tenant()
    print("ok")