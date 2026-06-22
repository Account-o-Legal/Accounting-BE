"""Accounting period locking.

The purpose of these tests is not merely "does ensure_period_open()
raise" — it's proving that the ledger services actually respect period
locks. A closed period that can still accept postings is worse than no
period lock at all because users think the books are frozen when they
aren't.

Run:
    uv run python -m app.modules.accounting_core.test_period_lock
"""

import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.core.exceptions import ValidationError
from app.modules.accounting_core.models import (
    Account,
    AccountingPeriod,
    JournalEntry,
    JournalLine,
)
from app.modules.accounting_core.services import post_journal_entry
from app.modules.accounting_core.void import void_journal_entry

TENANT_ID = "ws_period_lock_test"
ACTOR_ID = "user_period_lock_test"


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    return async_sessionmaker(
        engine,
        expire_on_commit=False,
    )


async def _seed_accounts(session_factory):
    async with session_factory() as db:
        bank = Account(
            tenant_id=TENANT_ID,
            code="1020",
            name="Bank",
            type="asset",
        )

        revenue = Account(
            tenant_id=TENANT_ID,
            code="4000",
            name="Revenue",
            type="revenue",
        )

        db.add_all([bank, revenue])
        await db.commit()

        await db.refresh(bank)
        await db.refresh(revenue)

        return bank.id, revenue.id


async def _create_closed_period(session_factory):
    async with session_factory() as db:
        period = AccountingPeriod(
            tenant_id=TENANT_ID,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            is_closed=True,
        )

        db.add(period)
        await db.commit()


async def _post_entry(
    session_factory,
    *,
    bank_id: str,
    revenue_id: str,
    entry_date: date,
):
    async with session_factory() as db:
        return await post_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry=JournalEntry(
                entry_date=entry_date,
                memo="Test Entry",
                source="manual",
            ),
            lines=[
                JournalLine(
                    account_id=bank_id,
                    debit=50000,
                    credit=0,
                ),
                JournalLine(
                    account_id=revenue_id,
                    debit=0,
                    credit=50000,
                ),
            ],
        )


#
# TEST 1
# Posting inside closed period must fail.
#

async def _run_posting_in_closed_period_is_blocked():
    session_factory = await _make_test_session_factory()

    bank_id, revenue_id = await _seed_accounts(session_factory)

    await _create_closed_period(session_factory)

    raised = False

    try:
        await _post_entry(
            session_factory,
            bank_id=bank_id,
            revenue_id=revenue_id,
            entry_date=date(2026, 1, 15),
        )
    except ValidationError as exc:
        raised = True
        assert "closed" in str(exc).lower()

    assert raised, "expected posting into closed period to fail"


#
# TEST 2
# Posting outside closed period must succeed.
#

async def _run_posting_in_open_period_is_allowed():
    session_factory = await _make_test_session_factory()

    bank_id, revenue_id = await _seed_accounts(session_factory)

    await _create_closed_period(session_factory)

    entry = await _post_entry(
        session_factory,
        bank_id=bank_id,
        revenue_id=revenue_id,
        entry_date=date(2026, 2, 15),
    )

    assert entry.id is not None


#
# TEST 3
# No period configured = posting allowed.
#

async def _run_posting_without_period_configuration_is_allowed():
    session_factory = await _make_test_session_factory()

    bank_id, revenue_id = await _seed_accounts(session_factory)

    entry = await _post_entry(
        session_factory,
        bank_id=bank_id,
        revenue_id=revenue_id,
        entry_date=date(2026, 1, 15),
    )

    assert entry.id is not None


#
# TEST 4
# Historical entry in closed period can still be voided today.
#

async def _run_voiding_closed_period_entry_with_today_reversal_is_allowed():
    session_factory = await _make_test_session_factory()

    bank_id, revenue_id = await _seed_accounts(session_factory)

    #
    # Create original BEFORE period is closed.
    #
    entry = await _post_entry(
        session_factory,
        bank_id=bank_id,
        revenue_id=revenue_id,
        entry_date=date(2026, 1, 15),
    )

    #
    # Close January afterwards.
    #
    await _create_closed_period(session_factory)

    async with session_factory() as db:
        voided = await void_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry_id=entry.id,
        )

    assert voided.id == entry.id


#
# TEST 5
# Backdating reversal into closed period must fail.
#

async def _run_backdated_void_into_closed_period_is_blocked():
    session_factory = await _make_test_session_factory()

    bank_id, revenue_id = await _seed_accounts(session_factory)

    entry = await _post_entry(
        session_factory,
        bank_id=bank_id,
        revenue_id=revenue_id,
        entry_date=date(2026, 1, 15),
    )

    await _create_closed_period(session_factory)

    raised = False

    async with session_factory() as db:
        try:
            await void_journal_entry(
                db,
                tenant_id=TENANT_ID,
                actor_user_id=ACTOR_ID,
                entry_id=entry.id,
                reversal_date=date(2026, 1, 15),
            )
        except ValidationError as exc:
            raised = True
            assert "closed" in str(exc).lower()

    assert raised, (
        "expected backdated reversal into closed period "
        "to be blocked"
    )


def test_posting_in_closed_period_is_blocked():
    asyncio.run(_run_posting_in_closed_period_is_blocked())


def test_posting_in_open_period_is_allowed():
    asyncio.run(_run_posting_in_open_period_is_allowed())


def test_posting_without_period_configuration_is_allowed():
    asyncio.run(_run_posting_without_period_configuration_is_allowed())


def test_voiding_closed_period_entry_with_today_reversal_is_allowed():
    asyncio.run(
        _run_voiding_closed_period_entry_with_today_reversal_is_allowed()
    )


def test_backdated_void_into_closed_period_is_blocked():
    asyncio.run(_run_backdated_void_into_closed_period_is_blocked())


if __name__ == "__main__":
    test_posting_in_closed_period_is_blocked()
    test_posting_in_open_period_is_allowed()
    test_posting_without_period_configuration_is_allowed()
    test_voiding_closed_period_entry_with_today_reversal_is_allowed()
    test_backdated_void_into_closed_period_is_blocked()

    print("ok")