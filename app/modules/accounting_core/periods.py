"""Accounting period controls.

Posting into a closed accounting period is prohibited. Period close is
the mechanism that freezes reported books so historical reports, tax
filings, and audits remain reproducible.

This file intentionally contains only period state transitions and
validation logic. Journal posting calls ensure_period_open(); reporting
never mutates periods.
"""

from datetime import date

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.accounting_core.models import AccountingPeriod


async def ensure_period_open(
    db: AsyncSession,
    *,
    tenant_id: str,
    posting_date: date,
) -> None:
    """Raise if posting_date falls inside a closed period."""
    result = await db.exec(
        select(AccountingPeriod).where(
            AccountingPeriod.tenant_id == tenant_id,
            AccountingPeriod.start_date <= posting_date,
            AccountingPeriod.end_date >= posting_date,
        )
    )

    period = result.first()

    if period and period.is_closed:
        raise ValidationError(
            f"Accounting period {period.start_date} to "
            f"{period.end_date} is closed"
        )


async def close_period(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str,
    period_id: str,
) -> AccountingPeriod:
    """Lock an accounting period against future postings."""
    period = (
        await db.exec(
            select(AccountingPeriod).where(
                AccountingPeriod.id == period_id,
                AccountingPeriod.tenant_id == tenant_id,
            )
        )
    ).first()

    if not period:
        raise NotFoundError("Accounting period not found")

    if period.is_closed:
        raise ValidationError("Accounting period is already closed")

    period.is_closed = True
    db.add(period)

    await db.commit()
    await db.refresh(period)

    return period


async def reopen_period(
    db: AsyncSession,
    *,
    tenant_id: str,
    period_id: str,
) -> AccountingPeriod:
    """Re-open a previously closed accounting period."""
    period = (
        await db.exec(
            select(AccountingPeriod).where(
                AccountingPeriod.id == period_id,
                AccountingPeriod.tenant_id == tenant_id,
            )
        )
    ).first()

    if not period:
        raise NotFoundError("Accounting period not found")

    if not period.is_closed:
        raise ValidationError("Accounting period is already open")

    period.is_closed = False
    db.add(period)

    await db.commit()
    await db.refresh(period)

    return period


async def close_fiscal_year(
    db: AsyncSession,
    *,
    tenant_id: str,
    fiscal_year: int,
) -> list[AccountingPeriod]:
    """Close every period ending within the specified fiscal year."""
    periods = (
        await db.exec(
            select(AccountingPeriod).where(
                AccountingPeriod.tenant_id == tenant_id,
                AccountingPeriod.end_date >= date(fiscal_year, 1, 1),
                AccountingPeriod.end_date <= date(fiscal_year, 12, 31),
            )
        )
    ).all()

    for period in periods:
        period.is_closed = True
        db.add(period)

    await db.commit()

    return list(periods)