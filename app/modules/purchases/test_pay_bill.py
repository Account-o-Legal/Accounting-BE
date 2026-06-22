"""Tests the complete two-entry bill lifecycle:

  1. create_bill  → debit Expense, credit AP
  2. pay_bill     → debit AP,      credit Bank

After both, AP must net to zero for this bill (the liability is cleared)
and the bank balance must reflect the cash outflow. The trial balance
must remain balanced throughout both steps.

Run: python -m app.modules.purchases.test_pay_bill
"""

import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import Account, JournalLine
from app.modules.purchases.models import BillCreate, VendorCreate
from app.modules.purchases.services import create_bill, create_vendor, pay_bill
from app.modules.banking.models import BankAccount

TENANT_ID = "ws_pay_bill_test"
ACTOR_ID = "user_pay_bill_test"


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(session_factory) -> dict[str, str]:
    async with session_factory() as db:
        ap = Account(tenant_id=TENANT_ID, code="2010", name="Accounts Payable", type="liability")
        utilities = Account(tenant_id=TENANT_ID, code="5100", name="Utilities", type="expense")
        bank_ledger = Account(tenant_id=TENANT_ID, code="1020", name="Bank Account", type="asset")
        db.add_all([ap, utilities, bank_ledger])
        await db.flush()
        bank_account = BankAccount(
            tenant_id=TENANT_ID, name="Primary", ledger_account_id=bank_ledger.id
        )
        db.add(bank_account)
        await db.commit()
        await db.refresh(ap)
        await db.refresh(utilities)
        await db.refresh(bank_ledger)
        await db.refresh(bank_account)
        return {
            "ap": ap.id,
            "utilities": utilities.id,
            "bank_ledger": bank_ledger.id,
            "bank_account": bank_account.id,
        }


async def _run_full_lifecycle_ap_nets_to_zero() -> None:
    session_factory = await _make_test_session_factory()
    ids = await _seed(session_factory)

    async with session_factory() as db:
        vendor = await create_vendor(
            db, tenant_id=TENANT_ID, actor_user_id=ACTOR_ID, body=VendorCreate(name="K-Electric")
        )

    async with session_factory() as db:
        bill = await create_bill(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            body=BillCreate(
                vendor_id=vendor.id,
                bill_date=date(2026, 6, 1),
                amount=25000,
                account_id=ids["utilities"],
            ),
        )

    # After create_bill: AP should have credit of 25,000 (liability)
    async with session_factory() as db:
        lines_after_create = (
            await db.exec(
                select(JournalLine).where(JournalLine.journal_entry_id == bill.journal_entry_id)
            )
        ).all()
    ap_credit = next(l for l in lines_after_create if l.account_id == ids["ap"])
    assert ap_credit.credit == 25000.0
    assert ap_credit.debit == 0.0

    async with session_factory() as db:
        paid_bill = await pay_bill(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            bill_id=bill.id,
            bank_account_id=ids["bank_account"],
        )

    assert paid_bill.is_paid is True

    # After pay_bill: sum all AP lines — debit from payment cancels the
    # original credit. Net AP for this bill should be zero.
    async with session_factory() as db:
        all_lines = (await db.exec(select(JournalLine))).all()

    ap_lines = [l for l in all_lines if l.account_id == ids["ap"]]
    net_ap = sum(l.credit - l.debit for l in ap_lines)
    assert net_ap == 0.0, f"AP should net to zero after payment, got {net_ap}"

    # Bank ledger should reflect the cash outflow (credit of 25,000)
    bank_lines = [l for l in all_lines if l.account_id == ids["bank_ledger"]]
    net_bank = sum(l.credit - l.debit for l in bank_lines)
    assert net_bank == 25000.0, f"Bank should show 25,000 outflow, got {net_bank}"

    # Trial balance must still be balanced across all entries
    total_debit = round(sum(l.debit for l in all_lines), 2)
    total_credit = round(sum(l.credit for l in all_lines), 2)
    assert total_debit == total_credit, f"Ledger unbalanced after payment: {total_debit} != {total_credit}"


async def _run_paying_already_paid_bill_rejected() -> None:
    session_factory = await _make_test_session_factory()
    ids = await _seed(session_factory)

    async with session_factory() as db:
        vendor = await create_vendor(
            db, tenant_id=TENANT_ID, actor_user_id=ACTOR_ID, body=VendorCreate(name="PTCL")
        )

    async with session_factory() as db:
        bill = await create_bill(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            body=BillCreate(
                vendor_id=vendor.id,
                bill_date=date(2026, 6, 1),
                amount=5000,
                account_id=ids["utilities"],
            ),
        )

    async with session_factory() as db:
        await pay_bill(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            bill_id=bill.id,
            bank_account_id=ids["bank_account"],
        )

    async with session_factory() as db:
        raised = False
        try:
            await pay_bill(
                db,
                tenant_id=TENANT_ID,
                actor_user_id=ACTOR_ID,
                bill_id=bill.id,
                bank_account_id=ids["bank_account"],
            )
        except Exception as exc:
            raised = True
            assert "already paid" in str(exc).lower()
        assert raised, "expected double-payment to be rejected"


def test_full_lifecycle_ap_nets_to_zero():
    asyncio.run(_run_full_lifecycle_ap_nets_to_zero())


def test_paying_already_paid_bill_rejected():
    asyncio.run(_run_paying_already_paid_bill_rejected())


if __name__ == "__main__":
    test_full_lifecycle_ap_nets_to_zero()
    test_paying_already_paid_bill_rejected()
    print("ok")