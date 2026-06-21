"""Tests explain_suggestion returns the real reason for a category, not
a hardcoded string — covers the three states a transaction can be in:
matched by an existing VendorRule, AI-suggested with no rule match, and
not yet categorized at all.

Run: python -m app.modules.ai.test_explain_suggestion
"""

import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import Account
from app.modules.ai.router import explain_suggestion
from app.modules.banking.models import BankTransaction
from app.modules.banking.rules import VendorRule

TENANT_ID = "ws_explain_test"


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _run_explains_a_rule_hit_by_naming_the_rule() -> None:
    session_factory = await _make_test_session_factory()
    async with session_factory() as db:
        utilities = Account(tenant_id=TENANT_ID, code="6010", name="Utilities", type="expense")
        db.add(utilities)
        await db.flush()

        db.add(VendorRule(tenant_id=TENANT_ID, vendor_pattern="k-electric", account_id=utilities.id))

        txn = BankTransaction(
            tenant_id=TENANT_ID,
            bank_account_id="bank1",
            txn_date=date(2026, 6, 1),
            description="K-Electric",
            amount=-25000,
            category_status="auto",
            suggested_account_id=utilities.id,
            confidence=1.0,
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)

        result = await explain_suggestion(txn_id=txn.id, workspace=TENANT_ID, db=db)

    assert "k-electric" in result["explanation"]
    assert "Utilities" in result["explanation"]
    assert "rule" in result["explanation"].lower()


async def _run_explains_an_ai_suggestion_with_no_matching_rule() -> None:
    session_factory = await _make_test_session_factory()
    async with session_factory() as db:
        misc = Account(tenant_id=TENANT_ID, code="5999", name="Miscellaneous Expense", type="expense")
        db.add(misc)
        await db.flush()

        txn = BankTransaction(
            tenant_id=TENANT_ID,
            bank_account_id="bank1",
            txn_date=date(2026, 6, 1),
            description="Unrecognized Vendor XYZ",
            amount=-500,
            category_status="ai_suggested",
            suggested_account_id=misc.id,
            confidence=0.62,
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)

        result = await explain_suggestion(txn_id=txn.id, workspace=TENANT_ID, db=db)

    assert "Miscellaneous Expense" in result["explanation"]
    assert "62%" in result["explanation"]
    # Must NOT claim a rule matched when none did — this is the bug being fixed.
    assert "vendor rule" not in result["explanation"].lower()


async def _run_explains_an_uncategorized_transaction_honestly() -> None:
    session_factory = await _make_test_session_factory()
    async with session_factory() as db:
        txn = BankTransaction(
            tenant_id=TENANT_ID,
            bank_account_id="bank1",
            txn_date=date(2026, 6, 1),
            description="Mystery Deposit",
            amount=1000,
            category_status="needs_review",
            suggested_account_id=None,
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)

        result = await explain_suggestion(txn_id=txn.id, workspace=TENANT_ID, db=db)

    assert "no category" in result["explanation"].lower()


def test_explains_a_rule_hit_by_naming_the_rule():
    asyncio.run(_run_explains_a_rule_hit_by_naming_the_rule())


def test_explains_an_ai_suggestion_with_no_matching_rule():
    asyncio.run(_run_explains_an_ai_suggestion_with_no_matching_rule())


def test_explains_an_uncategorized_transaction_honestly():
    asyncio.run(_run_explains_an_uncategorized_transaction_honestly())


if __name__ == "__main__":
    test_explains_a_rule_hit_by_naming_the_rule()
    test_explains_an_ai_suggestion_with_no_matching_rule()
    test_explains_an_uncategorized_transaction_honestly()
    print("ok")