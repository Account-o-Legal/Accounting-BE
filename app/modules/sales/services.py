"""Invoice business logic — the three things create_invoice in the router
used to get wrong, fixed together because they're genuinely coupled:
you can't compute a real invoice total (and therefore can't post it to
the ledger) without the lines actually existing first.

ponytail: invoice numbering is a per-tenant, per-year count query
(SELECT count(*) WHERE tenant_id=... AND issue_date in this year), not a
dedicated sequence table. Good enough at MVP concurrency (one accountant
creating invoices for one client at a time, not a high-throughput
checkout flow) — a real DB sequence or a SELECT FOR UPDATE counter row
is the upgrade if concurrent invoice creation ever produces a duplicate
number in practice.
"""

from datetime import date

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.audit import record_audit_event
from app.core.enums import InvoiceStatus
from app.core.exceptions import ValidationError
from app.modules.accounting_core.models import Account, JournalEntry, JournalLine
from app.modules.accounting_core.services import post_journal_entry
from app.modules.sales.models import Invoice, InvoiceCreate, InvoiceLine
from app.modules.tax.models import TaxRate

# Codes from config/jurisdictions/pk.json's default_chart_of_accounts.
# ponytail: hardcoded to the PK pack's codes, same as auth/router.py's
# "1020" bank-account lookup. Acceptable for an MVP that ships pk.json
# only (see config.py docstring) — revisit if/when a second jurisdiction
# pack uses different codes for these roles.
_ACCOUNTS_RECEIVABLE_CODE = "1200"
_SALES_REVENUE_CODE = "4000"
_GST_PAYABLE_CODE = "2200"


async def _next_invoice_number(db: AsyncSession, *, tenant_id: str, issue_date: date) -> str:
    """INV-<year>-<4-digit sequence>, sequence resets each calendar year,
    scoped per tenant (two different clients can both have INV-2026-0001
    without colliding — invoice_number is not globally unique, only
    unique enough to be human-readable per workspace).
    """
    year_start = date(issue_date.year, 1, 1)
    year_end = date(issue_date.year, 12, 31)
    count = (
        await db.exec(
            select(func.count(Invoice.id)).where(
                Invoice.tenant_id == tenant_id,
                Invoice.issue_date >= year_start,
                Invoice.issue_date <= year_end,
            )
        )
    ).one()
    return f"INV-{issue_date.year}-{count + 1:04d}"


async def _find_account_by_code(db: AsyncSession, *, tenant_id: str, code: str) -> Account | None:
    return (
        await db.exec(
            select(Account).where(Account.tenant_id == tenant_id, Account.code == code)
        )
    ).first()


async def create_invoice(
    db: AsyncSession, *, tenant_id: str, actor_user_id: str, body: InvoiceCreate
) -> Invoice:
    """Creates the invoice, persists every line (the bug being fixed:
    the router previously accepted body.lines and silently dropped them),
    assigns a real per-tenant sequential number, and posts the
    transaction to the ledger immediately: debit Accounts Receivable for
    the full total, credit Sales Revenue for the subtotal, credit GST
    Payable for any tax collected.

    ponytail: posts at creation (draft status), not at "send" or
    "payment received" — this is the simplest correct treatment given
    invoices don't have a separate "sent" workflow trigger yet. Real
    accounting practice often defers AR recognition to invoice issuance
    rather than draft creation; revisit if/when a real "send invoice"
    action exists as a distinct step from creation.
    """
    if not body.lines:
        raise ValidationError("Invoice must have at least one line")

    invoice_number = await _next_invoice_number(db, tenant_id=tenant_id, issue_date=body.issue_date)

    invoice = Invoice(
        tenant_id=tenant_id,
        customer_id=body.customer_id,
        invoice_number=invoice_number,
        issue_date=body.issue_date,
        due_date=body.due_date,
        status=InvoiceStatus.DRAFT,
    )
    db.add(invoice)
    await db.flush()

    subtotal = 0.0
    tax_total = 0.0
    tax_rate_cache: dict[str, float] = {}

    for line_in in body.lines:
        line_amount = round(line_in.quantity * line_in.unit_price, 2)
        subtotal += line_amount

        line_tax = 0.0
        if line_in.tax_rate_id:
            if line_in.tax_rate_id not in tax_rate_cache:
                rate = (
                    await db.exec(
                        select(TaxRate).where(
                            TaxRate.id == line_in.tax_rate_id, TaxRate.tenant_id == tenant_id
                        )
                    )
                ).first()
                if not rate:
                    raise ValidationError(f"Unknown tax_rate_id: {line_in.tax_rate_id}")
                tax_rate_cache[line_in.tax_rate_id] = rate.rate_percent
            line_tax = round(line_amount * tax_rate_cache[line_in.tax_rate_id] / 100, 2)
            tax_total += line_tax

        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
                description=line_in.description,
                quantity=line_in.quantity,
                unit_price=line_in.unit_price,
                tax_rate_id=line_in.tax_rate_id,
            )
        )

    subtotal = round(subtotal, 2)
    tax_total = round(tax_total, 2)
    total = round(subtotal + tax_total, 2)

    ar_account = await _find_account_by_code(db, tenant_id=tenant_id, code=_ACCOUNTS_RECEIVABLE_CODE)
    revenue_account = await _find_account_by_code(db, tenant_id=tenant_id, code=_SALES_REVENUE_CODE)
    if not ar_account or not revenue_account:
        # ponytail: fail loudly rather than silently skip posting — an
        # invoice that exists but never hit the ledger is exactly the bug
        # this function was written to fix. A workspace missing its
        # seeded CoA is a setup problem worth surfacing immediately, not
        # swallowing.
        raise ValidationError(
            "Workspace is missing required Accounts Receivable / Sales Revenue "
            "accounts — cannot post invoice to the ledger"
        )

    journal_lines = [
        JournalLine(account_id=ar_account.id, debit=total, credit=0),
        JournalLine(account_id=revenue_account.id, debit=0, credit=subtotal),
    ]

    if tax_total > 0:
        gst_account = await _find_account_by_code(db, tenant_id=tenant_id, code=_GST_PAYABLE_CODE)
        if not gst_account:
            raise ValidationError(
                "Invoice has tax lines but workspace is missing a GST Payable account"
            )
        journal_lines.append(JournalLine(account_id=gst_account.id, debit=0, credit=tax_total))

    posted_entry = await post_journal_entry(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entry=JournalEntry(
            entry_date=body.issue_date,
            memo=f"Invoice {invoice_number}",
            source="manual",
        ),
        lines=journal_lines,
    )

    invoice.journal_entry_id = posted_entry.id
    db.add(invoice)

    await record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="create",
        diff_json=f'{{"invoice_number": "{invoice_number}", "total": {total}}}',
    )

    await db.commit()
    await db.refresh(invoice)
    return invoice