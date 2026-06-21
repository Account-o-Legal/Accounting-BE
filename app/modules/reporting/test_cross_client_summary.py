"""Tests cross_client_summary directly (not through the FastAPI router
layer — calling the function with constructed dependency values, same
pattern as test_vendor_rule_learning.py calling approve_transaction
directly). Covers: per-workspace pending_review_count is correct, the
is_balanced trust signal reflects each workspace's actual trial balance,
and workspaces sort with the most pending work first.

Run: python -m app.modules.reporting.test_cross_client_summary
"""

import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import Account, JournalEntry, JournalLine
from app.modules.accounting_core.services import post_journal_entry
from app.modules.auth.models import User, Workspace, WorkspaceMember
from app.modules.banking.models import BankAccount, BankTransaction
from app.modules.reporting.router import cross_client_summary

USER_ID = "user_cross_client_test"


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_two_workspaces(session_factory) -> dict[str, str]:
    """Workspace A: 3 pending review-queue transactions, balanced books.
    Workspace B: 0 pending, balanced books. Same user is a member of both
    — mirrors the accountant-with-multiple-clients shape this endpoint
    exists for."""
    async with session_factory() as db:
        user = User(id=USER_ID, email="acct@example.com", password_hash="x")
        ws_a = Workspace(name="Client A")
        ws_b = Workspace(name="Client B")
        db.add_all([user, ws_a, ws_b])
        await db.flush()

        db.add_all(
            [
                WorkspaceMember(user_id=USER_ID, workspace_id=ws_a.id, role="owner"),
                WorkspaceMember(user_id=USER_ID, workspace_id=ws_b.id, role="owner"),
            ]
        )

        bank_a = Account(tenant_id=ws_a.id, code="1020", name="Bank Account", type="asset")
        revenue_a = Account(tenant_id=ws_a.id, code="4000", name="Sales Revenue", type="revenue")
        db.add_all([bank_a, revenue_a])
        await db.flush()

        bank_account_a = BankAccount(
            tenant_id=ws_a.id, name="Primary", ledger_account_id=bank_a.id
        )
        db.add(bank_account_a)
        await db.flush()

        # 3 pending transactions for Client A
        for i in range(3):
            db.add(
                BankTransaction(
                    tenant_id=ws_a.id,
                    bank_account_id=bank_account_a.id,
                    txn_date=date(2026, 6, i + 1),
                    description=f"Unknown Vendor {i}",
                    amount=-1000,
                    category_status="needs_review",
                )
            )

        await db.commit()
        return {"ws_a": ws_a.id, "ws_b": ws_b.id, "bank_a": bank_a.id, "revenue_a": revenue_a.id}


async def _run_cross_client_summary_reflects_pending_and_sorts() -> None:
    session_factory = await _make_test_session_factory()
    ids = await _seed_two_workspaces(session_factory)

    # Post one balanced entry in Client A so is_balanced has real activity
    # to check, not just the trivially-balanced empty case.
    async with session_factory() as db:
        await post_journal_entry(
            db,
            tenant_id=ids["ws_a"],
            actor_user_id=USER_ID,
            entry=JournalEntry(entry_date=date(2026, 6, 1), memo="Client Payment", source="manual"),
            lines=[
                JournalLine(account_id=ids["bank_a"], debit=5000, credit=0),
                JournalLine(account_id=ids["revenue_a"], debit=0, credit=5000),
            ],
        )

    async with session_factory() as db:
        result = await cross_client_summary(user={"sub": USER_ID}, db=db)

    workspaces = result["workspaces"]
    assert len(workspaces) == 2

    by_id = {w["workspace_id"]: w for w in workspaces}
    client_a = by_id[ids["ws_a"]]
    client_b = by_id[ids["ws_b"]]

    assert client_a["pending_review_count"] == 3
    assert client_a["is_balanced"] is True
    assert client_a["workspace_name"] == "Client A"

    assert client_b["pending_review_count"] == 0
    assert client_b["is_balanced"] is True  # empty workspace, trivially balanced
    assert client_b["workspace_name"] == "Client B"

    # Most pending work sorts first.
    assert workspaces[0]["workspace_id"] == ids["ws_a"]
    assert workspaces[1]["workspace_id"] == ids["ws_b"]


async def _run_user_with_no_workspaces_gets_empty_list() -> None:
    session_factory = await _make_test_session_factory()

    async with session_factory() as db:
        result = await cross_client_summary(user={"sub": "nobody"}, db=db)

    assert result == {"workspaces": []}


def test_cross_client_summary_reflects_pending_and_sorts():
    asyncio.run(_run_cross_client_summary_reflects_pending_and_sorts())


def test_user_with_no_workspaces_gets_empty_list():
    asyncio.run(_run_user_with_no_workspaces_gets_empty_list())


if __name__ == "__main__":
    test_cross_client_summary_reflects_pending_and_sorts()
    test_user_with_no_workspaces_gets_empty_list()
    print("ok")