from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import ValidationError
from app.modules.accounting_core.models import AccountingPeriod


async def ensure_period_open(
    db: AsyncSession,
    *,
    tenant_id: str,
    entry_date: date,
) -> None:
    """
    Prevent posting into a closed accounting period.

    A date is considered locked when it falls inside an
    closed AccountingPeriod.

    No-op if no matching period exists.
    """

    period = (
        (
            await db.execute(
                select(AccountingPeriod).where(
                    AccountingPeriod.tenant_id == tenant_id,
                    AccountingPeriod.start_date <= entry_date,
                    AccountingPeriod.end_date >= entry_date,
                )
            )
        )
        .scalars()
        .first()
    )

    if period and period.is_closed:
        raise ValidationError(
            f"Accounting period {period.start_date} to "
            f"{period.end_date} is closed"
        )