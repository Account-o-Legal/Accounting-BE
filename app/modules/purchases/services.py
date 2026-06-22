"""Purchases business logic — vendor creation, and bill creation with
ledger posting (the same gap class as sales/services.py's invoice fix:
a bill that exists but never hits the ledger is invisible to every
report). Posted as: debit the bill's chosen expense account, credit
Accounts Payable for the full amount, at bill creation time (not at
payment time — see the docstring on create_bill for why, same caveat
as invoices).
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.audit import record_audit_event
from app.core.exceptions import ValidationError
from app.modules.accounting_core.models import Account, JournalEntry, JournalLine
from app.modules.accounting_core.services import post_journal_entry
from app.modules.purchases.models import Bill, BillCreate, Vendor, VendorCreate

# From config/jurisdictions/pk.json's default_chart_of_accounts.
# ponytail: hardcoded to the PK pack's code, same caveat as
# sales/services.py's AR/Revenue/GST codes — revisit for a second
# jurisdiction pack with different codes.
_ACCOUNTS_PAYABLE_CODE = "2010"


async def create_vendor(
    db: AsyncSession, *, tenant_id: str, actor_user_id: str, body: VendorCreate
) -> Vendor:
    vendor = Vendor(tenant_id=tenant_id, name=body.name, email=body.email)
    db.add(vendor)
    await db.flush()
    await record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="vendor",
        entity_id=vendor.id,
        action="create",
        diff_json=f'{{"name": "{vendor.name}"}}',
    )
    await db.commit()
    await db.refresh(vendor)
    return vendor


async def _find_account_by_code(db: AsyncSession, *, tenant_id: str, code: str) -> Account | None:
    return (
        await db.exec(
            select(Account).where(Account.tenant_id == tenant_id, Account.code == code)
        )
    ).first()


async def create_bill(
    db: AsyncSession, *, tenant_id: str, actor_user_id: str, body: BillCreate
) -> Bill:
    """Creates the bill and immediately posts it to the ledger: debit
    body.account_id (the expense category the caller chose) for the full
    amount, credit Accounts Payable for the same amount.

    ponytail: posts at creation, not at payment. is_paid is tracked on
    the Bill row but doesn't trigger a second journal entry (the AP ->
    Bank payment posting) yet — that's a real future step ("mark bill as
    paid" should debit AP and credit the bank account, mirroring
    approve_transaction's bank-leg logic), not built here. Flagged
    rather than silently treating is_paid as cosmetic.
    """
    expense_account = (
        await db.exec(
            select(Account).where(Account.id == body.account_id, Account.tenant_id == tenant_id)
        )
    ).first()
    if not expense_account:
        raise ValidationError(f"Unknown account_id: {body.account_id}")

    ap_account = await _find_account_by_code(db, tenant_id=tenant_id, code=_ACCOUNTS_PAYABLE_CODE)
    if not ap_account:
        raise ValidationError(
            "Workspace is missing the Accounts Payable account — cannot post bill to the ledger"
        )

    bill = Bill(
        tenant_id=tenant_id,
        vendor_id=body.vendor_id,
        bill_date=body.bill_date,
        amount=body.amount,
        account_id=body.account_id,
        receipt_file_id=body.receipt_file_id,
    )
    db.add(bill)
    await db.flush()

    posted_entry = await post_journal_entry(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entry=JournalEntry(
            entry_date=body.bill_date,
            memo=f"Bill from vendor {body.vendor_id}",
            source="manual",
        ),
        lines=[
            JournalLine(account_id=expense_account.id, debit=body.amount, credit=0),
            JournalLine(account_id=ap_account.id, debit=0, credit=body.amount),
        ],
    )

    bill.journal_entry_id = posted_entry.id
    db.add(bill)

    await record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="bill",
        entity_id=bill.id,
        action="create",
        diff_json=f'{{"vendor_id": "{bill.vendor_id}", "amount": {bill.amount}}}',
    )

    await db.commit()
    await db.refresh(bill)
    return bill