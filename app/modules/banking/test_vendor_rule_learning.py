"""Tests the learning-loop addition to approve_transaction: resolving a
genuine rule-miss (category_status == "needs_review") should create a
VendorRule so the same vendor auto-categorizes on the next import. This
is the mechanism that makes "AI does the bookkeeping" actually improve
over time instead of staying at whatever rules existed on day one.

ponytail: in-memory SQLite, same pattern as test_import_worker.py and
test_trial_balance.py — this is a full DB read-modify-write cycle
(txn lookup, bank account lookup, journal posting, rule creation), not
pure logic, so it needs a real (if disposable) database to test honestly.

Run: python -m app.modules.banking.test_vendor_rule_learning
"""

import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import Account
from app.modules.banking.models import BankAccount, BankTransaction
from app.modules.banking.router import ApproveTransactionRequest, approve_transaction
from app.modules.banking.rules import VendorRule

TENANT_ID = "ws_rule_learning_test"
USER = {"sub": "user_rule_learning_test"}


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(session_factory) -> dict[str, str]:
    async with session_factory() as db:
        bank_ledger = Account(tenant_id=TENANT_ID, code="1020", name="Bank Account", type="asset")
        utilities = Account(tenant_id=TENANT_ID, code="6010", name="Utilities", type="expense")
        db.add_all([bank_ledger, utilities])
        await db.flush()

        bank_account = BankAccount(
            tenant_id=TENANT_ID, name="Primary", ledger_account_id=bank_ledger.id
        )
        db.add(bank_account)
        await db.commit()
        await db.refresh(bank_account)
        return {"bank_account_id": bank_account.id, "utilities_account_id": utilities.id}


async def _run_approving_rule_miss_creates_vendor_rule() -> None:
    session_factory = await _make_test_session_factory()
    ids = await _seed(session_factory)

    async with session_factory() as db:
        txn = BankTransaction(
            tenant_id=TENANT_ID,
            bank_account_id=ids["bank_account_id"],
            txn_date=date(2026, 6, 1),
            description="K-Electric",
            amount=-25000,
            category_status="needs_review",  # genuine rule-miss, no suggestion
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)

        await approve_transaction(
            txn_id=txn.id,
            workspace=TENANT_ID,
            user=USER,
            db=db,
            body=ApproveTransactionRequest(account_id=ids["utilities_account_id"]),
        )

    async with session_factory() as db:
        rules = (
            await db.exec(select(VendorRule).where(VendorRule.tenant_id == TENANT_ID))
        ).all()

    assert len(rules) == 1, f"expected exactly one VendorRule, got {len(rules)}"
    assert rules[0].vendor_pattern == "k-electric"
    assert rules[0].account_id == ids["utilities_account_id"]


async def _run_reapproving_existing_pattern_does_not_duplicate() -> None:
    """Two different K-Electric transactions, both starting as rule-misses
    (simulating: the first approval's rule hasn't been picked up by a
    re-import yet, or the accountant is clearing a backlog). The second
    approval must not create a second, possibly conflicting rule."""
    session_factory = await _make_test_session_factory()
    ids = await _seed(session_factory)

    async with session_factory() as db:
        txn1 = BankTransaction(
            tenant_id=TENANT_ID,
            bank_account_id=ids["bank_account_id"],
            txn_date=date(2026, 6, 1),
            description="K-Electric",
            amount=-25000,
            category_status="needs_review",
        )
        txn2 = BankTransaction(
            tenant_id=TENANT_ID,
            bank_account_id=ids["bank_account_id"],
            txn_date=date(2026, 7, 1),
            description="K-Electric",
            amount=-26000,
            category_status="needs_review",
        )
        db.add_all([txn1, txn2])
        await db.commit()
        await db.refresh(txn1)
        await db.refresh(txn2)

        await approve_transaction(
            txn_id=txn1.id,
            workspace=TENANT_ID,
            user=USER,
            db=db,
            body=ApproveTransactionRequest(account_id=ids["utilities_account_id"]),
        )

    async with session_factory() as db:
        txn2 = (await db.exec(select(BankTransaction).where(BankTransaction.id == txn2.id))).first()
        await approve_transaction(
            txn_id=txn2.id,
            workspace=TENANT_ID,
            user=USER,
            db=db,
            body=ApproveTransactionRequest(account_id=ids["utilities_account_id"]),
        )

    async with session_factory() as db:
        rules = (
            await db.exec(select(VendorRule).where(VendorRule.tenant_id == TENANT_ID))
        ).all()

    assert len(rules) == 1, f"expected the second approval to reuse the existing rule, got {len(rules)} rules"


async def _run_approving_rule_hit_does_not_create_duplicate_rule() -> None:
    """A transaction that already came in as 'auto' (rule hit) shouldn't
    spawn a second rule for the same vendor when approved/re-confirmed."""
    session_factory = await _make_test_session_factory()
    ids = await _seed(session_factory)

    async with session_factory() as db:
        db.add(
            VendorRule(
                tenant_id=TENANT_ID,
                vendor_pattern="k-electric",
                account_id=ids["utilities_account_id"],
            )
        )
        txn = BankTransaction(
            tenant_id=TENANT_ID,
            bank_account_id=ids["bank_account_id"],
            txn_date=date(2026, 6, 1),
            description="K-Electric",
            amount=-25000,
            category_status="auto",  # rule already matched on import
            suggested_account_id=ids["utilities_account_id"],
            confidence=1.0,
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)

        await approve_transaction(
            txn_id=txn.id, workspace=TENANT_ID, user=USER, db=db
        )

    async with session_factory() as db:
        rules = (
            await db.exec(select(VendorRule).where(VendorRule.tenant_id == TENANT_ID))
        ).all()

    assert len(rules) == 1, f"rule-hit approval should not create a new rule, got {len(rules)}"


def test_approving_rule_miss_creates_vendor_rule():
    asyncio.run(_run_approving_rule_miss_creates_vendor_rule())


def test_reapproving_existing_pattern_does_not_duplicate():
    asyncio.run(_run_reapproving_existing_pattern_does_not_duplicate())


def test_approving_rule_hit_does_not_create_duplicate_rule():
    asyncio.run(_run_approving_rule_hit_does_not_create_duplicate_rule())


if __name__ == "__main__":
    test_approving_rule_miss_creates_vendor_rule()
    test_reapproving_existing_pattern_does_not_duplicate()
    test_approving_rule_hit_does_not_create_duplicate_rule()
    print("ok")