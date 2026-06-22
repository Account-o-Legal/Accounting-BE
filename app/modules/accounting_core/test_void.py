"""The highest-stakes test in this codebase, alongside test_services.py's
balance check: voiding is the one operation with a real failure mode
worse than "wrong number" — a partially-failed void could leave a
transaction's money effect either duplicated (original still POSTED
AND a reversal posted) or vanished (original silently mutated/deleted).
This test proves: the original is never touched except its status field,
the reversal exactly nets the original to zero, double-voiding is
rejected, and the default reversal date is today (not the original's
date) unless explicitly overridden.

Run: python -m app.modules.accounting_core.test_void
"""

import asyncio
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.enums import JournalEntryStatus
from app.core.exceptions import ValidationError
from app.modules.accounting_core.models import Account, JournalEntry, JournalLine
from app.modules.accounting_core.services import post_journal_entry
from app.modules.accounting_core.void import void_journal_entry
from app.modules.reporting.services import generate_trial_balance

TENANT_ID = "ws_void_test"
ACTOR_ID = "user_void_test"


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_accounts_and_post_entry(session_factory) -> dict[str, str]:
    async with session_factory() as db:
        bank = Account(tenant_id=TENANT_ID, code="1020", name="Bank Account", type="asset")
        revenue = Account(tenant_id=TENANT_ID, code="4000", name="Sales Revenue", type="revenue")
        db.add_all([bank, revenue])
        await db.commit()
        await db.refresh(bank)
        await db.refresh(revenue)

    async with session_factory() as db:
        entry = await post_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry=JournalEntry(entry_date=date(2026, 5, 1), memo="Client Payment", source="manual"),
            lines=[
                JournalLine(account_id=bank.id, debit=50000, credit=0),
                JournalLine(account_id=revenue.id, debit=0, credit=50000),
            ],
        )

    return {"bank": bank.id, "revenue": revenue.id, "entry_id": entry.id}


async def _run_void_nets_to_zero_and_preserves_original() -> None:
    session_factory = await _make_test_session_factory()
    ids = await _seed_accounts_and_post_entry(session_factory)

    async with session_factory() as db:
        voided = await void_journal_entry(
            db, tenant_id=TENANT_ID, actor_user_id=ACTOR_ID, entry_id=ids["entry_id"]
        )

    assert voided.status == JournalEntryStatus.VOID

    async with session_factory() as db:
        # Original's lines must be byte-for-byte unchanged — void NEVER
        # mutates line amounts, only the parent entry's status.
        original_lines = (
            await db.exec(select(JournalLine).where(JournalLine.journal_entry_id == ids["entry_id"]))
        ).all()
    by_account = {l.account_id: l for l in original_lines}
    assert by_account[ids["bank"]].debit == 50000.0
    assert by_account[ids["revenue"]].credit == 50000.0

    async with session_factory() as db:
        # Reports include BOTH the voided original and its reversal
        # (visible history, per reporting/services.py's design) — since
        # a reversal is always the exact mirror of what it reverses,
        # including both means every affected account's NET balance
        # returns to zero automatically, while total_debit/total_credit
        # reflect the real combined activity of both entries (100000
        # each here, not zero) — that's the actual proof the void
        # worked: real history stays visible, AND the net effect is gone.
        tb = await generate_trial_balance(db, tenant_id=TENANT_ID)

    assert tb["is_balanced"] is True
    assert tb["total_debit"] == tb["total_credit"] == 100000.0

    by_code = {a["code"]: a for a in tb["accounts"]}
    assert by_code["1020"]["balance"] == 0.0, (
        f"bank account's net balance should be zero after void+reversal, "
        f"got {by_code['1020']['balance']}"
    )
    assert by_code["4000"]["balance"] == 0.0, (
        f"revenue account's net balance should be zero after void+reversal, "
        f"got {by_code['4000']['balance']}"
    )

async def _run_double_void_is_rejected() -> None:
    session_factory = await _make_test_session_factory()
    ids = await _seed_accounts_and_post_entry(session_factory)

    async with session_factory() as db:
        await void_journal_entry(
            db, tenant_id=TENANT_ID, actor_user_id=ACTOR_ID, entry_id=ids["entry_id"]
        )

    async with session_factory() as db:
        raised = False
        try:
            await void_journal_entry(
                db, tenant_id=TENANT_ID, actor_user_id=ACTOR_ID, entry_id=ids["entry_id"]
            )
        except ValidationError as exc:
            raised = True
            assert "only posted entries" in str(exc).lower()
        assert raised, "expected voiding an already-VOID entry to be rejected"


async def _run_default_reversal_date_is_today_not_original() -> None:
    """The compliance-sensitive default: voiding an entry from last month
    must NOT silently backdate the reversal into that closed period."""
    session_factory = await _make_test_session_factory()
    ids = await _seed_accounts_and_post_entry(session_factory)  # original dated 2026-05-01

    async with session_factory() as db:
        await void_journal_entry(
            db, tenant_id=TENANT_ID, actor_user_id=ACTOR_ID, entry_id=ids["entry_id"]
        )

    async with session_factory() as db:
        all_entries = (
            await db.exec(select(JournalEntry).where(JournalEntry.tenant_id == TENANT_ID))
        ).all()
    reversal = next(e for e in all_entries if e.source == "reversal")

    assert reversal.entry_date == date.today(), (
        f"expected reversal dated today ({date.today()}), got {reversal.entry_date} "
        "— defaulting to the original entry's date would silently backdate "
        "into a possibly-already-reported period"
    )


async def _run_explicit_reversal_date_override_is_honored() -> None:
    """The opt-in escape hatch: same-day fix, explicitly choosing to
    reverse on the original's own date."""
    session_factory = await _make_test_session_factory()
    ids = await _seed_accounts_and_post_entry(session_factory)

    async with session_factory() as db:
        await void_journal_entry(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            entry_id=ids["entry_id"],
            reversal_date=date(2026, 5, 1),  # explicitly match the original's date
        )

    async with session_factory() as db:
        all_entries = (
            await db.exec(select(JournalEntry).where(JournalEntry.tenant_id == TENANT_ID))
        ).all()
    reversal = next(e for e in all_entries if e.source == "reversal")

    assert reversal.entry_date == date(2026, 5, 1)


async def _run_voiding_nonexistent_entry_raises_not_found() -> None:
    session_factory = await _make_test_session_factory()
    await _seed_accounts_and_post_entry(session_factory)

    async with session_factory() as db:
        from app.core.exceptions import NotFoundError

        raised = False
        try:
            await void_journal_entry(
                db, tenant_id=TENANT_ID, actor_user_id=ACTOR_ID, entry_id="nonexistent"
            )
        except NotFoundError:
            raised = True
        assert raised


def test_void_nets_to_zero_and_preserves_original():
    asyncio.run(_run_void_nets_to_zero_and_preserves_original())


def test_double_void_is_rejected():
    asyncio.run(_run_double_void_is_rejected())


def test_default_reversal_date_is_today_not_original():
    asyncio.run(_run_default_reversal_date_is_today_not_original())


def test_explicit_reversal_date_override_is_honored():
    asyncio.run(_run_explicit_reversal_date_override_is_honored())


def test_voiding_nonexistent_entry_raises_not_found():
    asyncio.run(_run_voiding_nonexistent_entry_raises_not_found())


if __name__ == "__main__":
    test_void_nets_to_zero_and_preserves_original()
    test_double_void_is_rejected()
    test_default_reversal_date_is_today_not_original()
    test_explicit_reversal_date_override_is_honored()
    test_voiding_nonexistent_entry_raises_not_found()
    print("ok")