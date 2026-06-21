"""Exercises process_bank_statement end-to-end without a live Postgres —
uses an in-memory SQLite async engine instead, and monkeypatches the
worker's `async_session` to point at it. This is the only way to test
this function honestly: it isn't pure logic (unlike test_services.py /
test_seed.py / test_approve_transaction.py), it's a full DB read-modify-
write cycle, so the test has to give it a real (if disposable) database.

ponytail: SQLite stands in for Postgres here. Good enough to prove the
import -> rule-match -> needs_review wiring is correct; NOT a substitute
for running this against real Postgres before trusting it with FK/type
edge cases Postgres enforces that SQLite doesn't.

Run: python -m app.workers.test_import_worker
"""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import SQLModel

# Import every model touched by process_bank_statement so SQLModel.metadata
# actually knows about their tables before create_all runs.
from app.modules.accounting_core.models import Account  # noqa: F401
from app.modules.banking.models import BankAccount, BankTransaction
from app.modules.banking.rules import VendorRule

import app.workers.import_worker as import_worker
from app.workers.import_worker import _parse_csv, process_bank_statement

TENANT_ID = "ws_test01"

CSV_BYTES = (
    "Date,Description,Amount\n"
    "2026-06-01,K-Electric,-25000\n"
    "2026-06-02,Unknown Client Deposit,150000\n"
).encode("utf-8")


def test_parse_csv_reads_date_description_amount():
    """Pure-function check, no DB needed."""
    rows = _parse_csv(CSV_BYTES)
    assert len(rows) == 2
    assert rows[0]["description"] == "K-Electric"
    assert rows[0]["amount"] == -25000.0
    assert rows[1]["amount"] == 150000.0


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_workspace(session_factory) -> tuple[str, str]:
    """Creates one expense account, one bank-ledger account, a BankAccount
    pointed at it, and a vendor rule matching 'k-electric' -> expense
    account. Returns (expense_account_id, bank_account_id) for assertions.
    """
    async with session_factory() as db:
        expense_account = Account(
            tenant_id=TENANT_ID, code="6010", name="Utilities", type="expense"
        )
        bank_ledger_account = Account(
            tenant_id=TENANT_ID, code="1020", name="Bank Account", type="asset"
        )
        db.add(expense_account)
        db.add(bank_ledger_account)
        await db.flush()

        bank_account = BankAccount(
            tenant_id=TENANT_ID,
            name="Primary Bank Account",
            ledger_account_id=bank_ledger_account.id,
        )
        db.add(bank_account)

        db.add(
            VendorRule(
                tenant_id=TENANT_ID,
                vendor_pattern="k-electric",
                account_id=expense_account.id,
            )
        )
        await db.commit()
        await db.refresh(bank_account)
        return expense_account.id, bank_account.id


async def _run_import_with_seeded_workspace() -> None:
    session_factory = await _make_test_session_factory()
    expense_account_id, bank_account_id = await _seed_workspace(session_factory)

    # Point the worker module's async_session at our in-memory test DB
    # instead of the real Postgres one for the duration of this call.
    original_async_session = import_worker.async_session
    import_worker.async_session = session_factory
    try:
        result = await process_bank_statement(
            ctx={}, workspace_id=TENANT_ID, file_bytes=CSV_BYTES
        )
    finally:
        import_worker.async_session = original_async_session

    assert result == {"imported": 2}, result

    async with session_factory() as db:
        txns = (
            await db.exec(
                select(BankTransaction).where(
                    BankTransaction.tenant_id == TENANT_ID
                )
            )
        ).all()

    assert len(txns) == 2

    matched = next(t for t in txns if t.description == "K-Electric")
    unmatched = next(t for t in txns if t.description == "Unknown Client Deposit")

    # Rule hit: auto-categorized against the expense account, full confidence.
    assert matched.category_status == "auto"
    assert matched.suggested_account_id == expense_account_id
    assert matched.confidence == 1.0
    assert matched.bank_account_id == bank_account_id

    # Rule miss: parked for human review, no guess made.
    assert unmatched.category_status == "needs_review"
    assert unmatched.suggested_account_id is None
    assert unmatched.confidence is None


async def _run_import_with_no_bank_account_raises() -> None:
    session_factory = await _make_test_session_factory()
    # Deliberately skip _seed_workspace — no BankAccount exists for this tenant.

    original_async_session = import_worker.async_session
    import_worker.async_session = session_factory
    try:
        raised = False
        try:
            await process_bank_statement(
                ctx={}, workspace_id="ws_empty", file_bytes=CSV_BYTES
            )
        except ValueError as exc:
            raised = True
            assert "no bank account" in str(exc).lower()
        assert raised, "expected ValueError when workspace has no BankAccount"
    finally:
        import_worker.async_session = original_async_session


def test_process_bank_statement_categorizes_known_vendor_and_queues_unknown():
    asyncio.run(_run_import_with_seeded_workspace())


def test_process_bank_statement_raises_without_bank_account():
    asyncio.run(_run_import_with_no_bank_account_raises())


if __name__ == "__main__":
    test_parse_csv_reads_date_description_amount()
    test_process_bank_statement_categorizes_known_vendor_and_queues_unknown()
    test_process_bank_statement_raises_without_bank_account()
    print("ok")