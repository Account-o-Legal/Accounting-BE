import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.enums import JournalEntryStatus
from app.core.exceptions import ValidationError
from app.modules.accounting_core.models import JournalEntry
from app.modules.accounting_core.void import void_journal_entry

TENANT_ID = "tenant-a"
ACTOR_ID = "user-a"


async def _run() -> None:
    engine = create_async_engine("sqlite+aiosqlite://", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine) as db:
        draft = JournalEntry(
            tenant_id=TENANT_ID,
            entry_date=date.today(),
            status=JournalEntryStatus.DRAFT,
        )

        db.add(draft)
        await db.commit()
        await db.refresh(draft)

        try:
            await void_journal_entry(
                db,
                tenant_id=TENANT_ID,
                actor_user_id=ACTOR_ID,
                entry_id=draft.id,
            )
            raise AssertionError("Expected ValidationError")
        except ValidationError:
            pass


def test_void_draft_entry() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_void_draft_entry()
    print("ok")