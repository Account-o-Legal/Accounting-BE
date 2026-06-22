"""Tests the three things create_invoice used to get wrong, fixed
together in sales/services.py: lines actually persist, invoice_number
is real and sequential (not a hardcoded collision), and the invoice
posts a balanced AR/Revenue/GST entry to the ledger immediately.

ponytail: in-memory SQLite, same pattern as every other DB-touching
test in this codebase (test_import_worker, test_trial_balance,
test_vendor_rule_learning).

Run: python -m app.modules.sales.test_create_invoice
"""

import asyncio
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.modules.accounting_core.models import Account, JournalLine
from app.modules.sales.models import Invoice, InvoiceCreate, InvoiceLine, InvoiceLineCreate
from app.modules.sales.services import create_invoice
from app.modules.tax.models import TaxRate

TENANT_ID = "ws_invoice_test"
ACTOR_ID = "user_invoice_test"


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_accounts_and_tax(session_factory) -> dict[str, str]:
    async with session_factory() as db:
        ar = Account(tenant_id=TENANT_ID, code="1200", name="Accounts Receivable", type="asset")
        revenue = Account(tenant_id=TENANT_ID, code="4000", name="Sales Revenue", type="revenue")
        gst_payable = Account(tenant_id=TENANT_ID, code="2200", name="GST Payable", type="liability")
        db.add_all([ar, revenue, gst_payable])
        await db.flush()

        gst_rate = TaxRate(tenant_id=TENANT_ID, name="GST 17%", rate_percent=17, is_default=True)
        db.add(gst_rate)
        await db.commit()
        await db.refresh(ar)
        await db.refresh(revenue)
        await db.refresh(gst_payable)
        await db.refresh(gst_rate)
        return {
            "ar": ar.id,
            "revenue": revenue.id,
            "gst_payable": gst_payable.id,
            "gst_rate": gst_rate.id,
        }


async def _run_lines_actually_persist() -> None:
    """The core bug: body.lines was accepted and silently dropped."""
    session_factory = await _make_test_session_factory()
    ids = await _seed_accounts_and_tax(session_factory)

    async with session_factory() as db:
        invoice = await create_invoice(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            body=InvoiceCreate(
                customer_id="cust1",
                issue_date=date(2026, 6, 1),
                due_date=date(2026, 6, 30),
                lines=[
                    InvoiceLineCreate(description="Consulting", quantity=10, unit_price=1000),
                    InvoiceLineCreate(description="Design work", quantity=1, unit_price=5000),
                ],
            ),
        )

    async with session_factory() as db:
        lines = (
            await db.exec(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
        ).all()

    assert len(lines) == 2, f"expected 2 persisted lines, got {len(lines)}"
    descriptions = {l.description for l in lines}
    assert descriptions == {"Consulting", "Design work"}


async def _run_invoice_numbers_are_sequential_per_tenant_per_year() -> None:
    session_factory = await _make_test_session_factory()
    await _seed_accounts_and_tax(session_factory)

    numbers = []
    for i in range(3):
        async with session_factory() as db:
            invoice = await create_invoice(
                db,
                tenant_id=TENANT_ID,
                actor_user_id=ACTOR_ID,
                body=InvoiceCreate(
                    customer_id="cust1",
                    issue_date=date(2026, 6, 1 + i),
                    due_date=date(2026, 6, 30),
                    lines=[InvoiceLineCreate(description="Item", quantity=1, unit_price=100)],
                ),
            )
            numbers.append(invoice.invoice_number)

    assert numbers == ["INV-2026-0001", "INV-2026-0002", "INV-2026-0003"], numbers


async def _run_invoice_with_tax_posts_balanced_entry_with_gst() -> None:
    session_factory = await _make_test_session_factory()
    ids = await _seed_accounts_and_tax(session_factory)

    async with session_factory() as db:
        invoice = await create_invoice(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            body=InvoiceCreate(
                customer_id="cust1",
                issue_date=date(2026, 6, 1),
                due_date=date(2026, 6, 30),
                lines=[
                    InvoiceLineCreate(
                        description="Consulting",
                        quantity=1,
                        unit_price=10000,
                        tax_rate_id=ids["gst_rate"],
                    ),
                ],
            ),
        )

    assert invoice.journal_entry_id is not None

    async with session_factory() as db:
        lines = (
            await db.exec(
                select(JournalLine).where(JournalLine.journal_entry_id == invoice.journal_entry_id)
            )
        ).all()

    by_account = {l.account_id: l for l in lines}
    # 10,000 subtotal, 17% GST = 1,700 tax, 11,700 total
    assert by_account[ids["ar"]].debit == 11700.0
    assert by_account[ids["revenue"]].credit == 10000.0
    assert by_account[ids["gst_payable"]].credit == 1700.0

    total_debit = sum(l.debit for l in lines)
    total_credit = sum(l.credit for l in lines)
    assert round(total_debit - total_credit, 2) == 0  # balanced, per post_journal_entry's own rule


async def _run_invoice_without_tax_posts_no_gst_line() -> None:
    session_factory = await _make_test_session_factory()
    ids = await _seed_accounts_and_tax(session_factory)

    async with session_factory() as db:
        invoice = await create_invoice(
            db,
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            body=InvoiceCreate(
                customer_id="cust1",
                issue_date=date(2026, 6, 1),
                due_date=date(2026, 6, 30),
                lines=[InvoiceLineCreate(description="Exempt item", quantity=1, unit_price=5000)],
            ),
        )

    async with session_factory() as db:
        lines = (
            await db.exec(
                select(JournalLine).where(JournalLine.journal_entry_id == invoice.journal_entry_id)
            )
        ).all()

    assert len(lines) == 2  # AR + Revenue only, no GST line
    assert ids["gst_payable"] not in [l.account_id for l in lines]


async def _run_empty_lines_rejected() -> None:
    session_factory = await _make_test_session_factory()
    await _seed_accounts_and_tax(session_factory)

    async with session_factory() as db:
        raised = False
        try:
            await create_invoice(
                db,
                tenant_id=TENANT_ID,
                actor_user_id=ACTOR_ID,
                body=InvoiceCreate(
                    customer_id="cust1",
                    issue_date=date(2026, 6, 1),
                    due_date=date(2026, 6, 30),
                    lines=[],
                ),
            )
        except Exception as exc:
            raised = True
            assert "at least one line" in str(exc).lower()
        assert raised, "expected an empty-lines invoice to be rejected"


def test_lines_actually_persist():
    asyncio.run(_run_lines_actually_persist())


def test_invoice_numbers_are_sequential_per_tenant_per_year():
    asyncio.run(_run_invoice_numbers_are_sequential_per_tenant_per_year())


def test_invoice_with_tax_posts_balanced_entry_with_gst():
    asyncio.run(_run_invoice_with_tax_posts_balanced_entry_with_gst())


def test_invoice_without_tax_posts_no_gst_line():
    asyncio.run(_run_invoice_without_tax_posts_no_gst_line())


def test_empty_lines_rejected():
    asyncio.run(_run_empty_lines_rejected())


if __name__ == "__main__":
    test_lines_actually_persist()
    test_invoice_numbers_are_sequential_per_tenant_per_year()
    test_invoice_with_tax_posts_balanced_entry_with_gst()
    test_invoice_without_tax_posts_no_gst_line()
    test_empty_lines_rejected()
    print("ok")