import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import AccountingPeriod
from app.modules.accounting_core.periods import close_period

TENANT_ID = "tenant-a"


async def _run():
    engine = create_async_engine("sqlite+aiosqlite://", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine) as db:
        year_end = AccountingPeriod(
            tenant_id=TENANT_ID,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_closed=False,
        )

        db.add(year_end)
        
        # 1. Flush to get the database ID assigned
        await db.flush()
        period_id = year_end.id
        
        # 2. Commit safely
        await db.commit()

        # 3. Pass the extracted ID and required audit argument
        await close_period(
            db,
            tenant_id=TENANT_ID,
            period_id=period_id,
            actor_user_id="test-user-id",
        )

        # 4. Explicitly refresh the object using 'await' to assert its state safely
        await db.refresh(year_end)

        assert year_end.is_closed is True

def test_year_end_close():
    asyncio.run(_run())


if __name__ == "__main__":
    test_year_end_close()
    print("ok")