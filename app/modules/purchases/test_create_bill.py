"""Tests the two purchases gaps fixed together: POST /vendors didn't
exist at all (Bill.vendor_id had nothing to point at), and bills never
posted to the ledger (invisible to every report, same bug class as
invoices before sales/services.py's fix).

Run: python -m app.modules.purchases.test_create_bill
"""

import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import Account, JournalLine
from app.modules.purchases.models import Bill, BillCreate, VendorCreate
from app.modules.purchases.services import create_bill, create_vendor

TENANT_ID = "ws_bill_test"
ACTOR_ID = "user_bill_test"


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_accounts(session_factory) -> dict[str, str]:
    async with session_factory() as db:
        ap = Account(tenant_id=TENANT_ID, code="2010", name="Accounts Payable", type="liability")
        utilities = Account(tenant_id=TENANT_ID, code="5100", name="Utilities", type="expense")
        db.add_all([ap, utilities])
        await db.commit()
        await db.refresh(ap)
        await db.refresh(utilities)
        return {"ap": ap.id, "utilities": utilities.id}


async def _run_create_vendor_works() -> None:
    session_factory = await _make_test_session_factory()
    async with session_factory() as db:
        vendor = await create_vendor(
            db, tenant_id=TENANT_ID, actor_user_id=ACTOR_ID, body=VendorCreate(name="K-Electric")
        )
    assert vendor.id is not None
    assert vendor.name == "K-Electric"


async def _run_bill_posts_balanced_expense_and_ap() -> None:
    session_factory = await _make_test_session_factory()
    ids = await _seed_accounts(session_factory)

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

    assert bill.journal_entry_id is not None

    async with session_factory() as db:
        lines = (
            await db.exec(
                select(JournalLine).where(JournalLine.journal_entry_id == bill.journal_entry_id)
            )
        ).all()

    by_account = {l.account_id: l for l in lines}
    assert by_account[ids["utilities"]].debit == 25000.0
    assert by_account[ids["ap"]].credit == 25000.0

    total_debit = sum(l.debit for l in lines)
    total_credit = sum(l.credit for l in lines)
    assert round(total_debit - total_credit, 2) == 0


async def _run_bill_with_unknown_account_rejected() -> None:
    session_factory = await _make_test_session_factory()
    await _seed_accounts(session_factory)

    async with session_factory() as db:
        vendor = await create_vendor(
            db, tenant_id=TENANT_ID, actor_user_id=ACTOR_ID, body=VendorCreate(name="K-Electric")
        )

    async with session_factory() as db:
        raised = False
        try:
            await create_bill(
                db,
                tenant_id=TENANT_ID,
                actor_user_id=ACTOR_ID,
                body=BillCreate(
                    vendor_id=vendor.id,
                    bill_date=date(2026, 6, 1),
                    amount=1000,
                    account_id="nonexistent_account",
                ),
            )
        except Exception as exc:
            raised = True
            assert "unknown account_id" in str(exc).lower()
        assert raised, "expected an unknown account_id to be rejected"


def test_create_vendor_works():
    asyncio.run(_run_create_vendor_works())


def test_bill_posts_balanced_expense_and_ap():
    asyncio.run(_run_bill_posts_balanced_expense_and_ap())


def test_bill_with_unknown_account_rejected():
    asyncio.run(_run_bill_with_unknown_account_rejected())


if __name__ == "__main__":
    test_create_vendor_works()
    test_bill_posts_balanced_expense_and_ap()
    test_bill_with_unknown_account_rejected()
    print("ok")