import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import ValidationError
from app.modules.accounting_core.models import (
    Account,
    JournalEntry,
    JournalLine,
)
from app.modules.accounting_core.services import post_journal_entry
from app.modules.accounting_core.void import void_journal_entry

TENANT_ID = "tenant-a"
ACTOR_ID = "user-a"


async def _run() -> None:
    engine = create_async_engine("sqlite+aiosqlite://", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as db:
        cash = Account(
            tenant_id=TENANT_ID,
            code="1000",
            name="Cash",
            type="asset",
        )

        equity = Account(
            tenant_id=TENANT_ID,
            code="3000",
            name="Equity",
            type="equity",
        )

        db.add(cash)
        db.add(equity)
        await db.commit()

        posted = await post_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry=JournalEntry(
                tenant_id=TENANT_ID,
                entry_date=date.today(),
            ),
            lines=[
                JournalLine(account_id=cash.id, debit=100, credit=0),
                JournalLine(account_id=equity.id, debit=0, credit=100),
            ],
        )

        await void_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry_id=posted.id,
        )

        try:
            await void_journal_entry(
                db,
                tenant_id=TENANT_ID,
                actor_user_id=ACTOR_ID,
                entry_id=posted.id,
            )
            raise AssertionError("Expected ValidationError")
        except ValidationError:
            pass


def test_void_already_voided() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_void_already_voided()
    print("ok")