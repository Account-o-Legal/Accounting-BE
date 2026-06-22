import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import AccountingPeriod
from app.modules.accounting_core.periods import (
    close_period,
    reopen_period,
)

TENANT_ID = "tenant-a"


async def _run():
    engine = create_async_engine("sqlite+aiosqlite://", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        
    async with AsyncSession(engine) as db:
        period = AccountingPeriod(
            tenant_id=TENANT_ID,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            is_closed=False,
        )
        db.add(period)
        
        await db.flush() 
        period_id = period.id 
        await db.commit()
        
        # Pass the missing actor_user_id keyword argument here
        await close_period(
            db,
            tenant_id=TENANT_ID,
            period_id=period_id,
            actor_user_id="test-user-id",
        )
        
        # You will likely need it here too!
        await reopen_period(
            db,
            tenant_id=TENANT_ID,
            period_id=period_id,
        )

def test_period_reopen():
    asyncio.run(_run())


if __name__ == "__main__":
    test_period_reopen()
    print("ok")