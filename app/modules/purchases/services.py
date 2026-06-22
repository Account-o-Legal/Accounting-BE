"""Purchases business logic — vendor creation, bill creation with ledger
posting, and bill payment posting.

Two-entry bill lifecycle:
  1. create_bill: debit Expense, credit AP   (you owe money)
  2. pay_bill:    debit AP,      credit Bank (you paid it)

After both entries, AP nets to zero for this bill and the bank balance
reflects the cash outflow — the books are correct.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.audit import record_audit_event
from app.core.exceptions import ValidationError
from app.modules.accounting_core.models import Account, JournalEntry, JournalLine
from app.modules.accounting_core.services import post_journal_entry
from app.modules.banking.models import BankAccount
from app.modules.purchases.models import Bill, BillCreate, Vendor, VendorCreate

_ACCOUNTS_PAYABLE_CODE = "2010"


async def _find_account_by_code(db: AsyncSession, *, tenant_id: str, code: str) -> Account | None:
    return (
        await db.exec(
            select(Account).where(Account.tenant_id == tenant_id, Account.code == code)
        )
    ).first()


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


async def create_bill(
    db: AsyncSession, *, tenant_id: str, actor_user_id: str, body: BillCreate
) -> Bill:
    """Creates the bill and posts entry 1: debit Expense, credit AP."""
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


async def pay_bill(
    db: AsyncSession, *, tenant_id: str, actor_user_id: str, bill_id: str, bank_account_id: str
) -> Bill:
    """Posts entry 2: debit AP (clearing the liability), credit Bank
    (cash out). Makes is_paid cosmetic status actually meaningful in
    the books — without this, a "paid" bill still showed an open AP
    liability on the balance sheet.
    """
    bill = (
        await db.exec(select(Bill).where(Bill.id == bill_id, Bill.tenant_id == tenant_id))
    ).first()
    if not bill:
        raise ValidationError("Bill not found")
    if bill.is_paid:
        raise ValidationError("Bill is already paid")

    ap_account = await _find_account_by_code(db, tenant_id=tenant_id, code=_ACCOUNTS_PAYABLE_CODE)
    if not ap_account:
        raise ValidationError("Workspace is missing the Accounts Payable account")

    bank_account = (
        await db.exec(
            select(BankAccount).where(
                BankAccount.id == bank_account_id, BankAccount.tenant_id == tenant_id
            )
        )
    ).first()
    if not bank_account:
        raise ValidationError(f"Bank account not found: {bank_account_id}")

    bank_ledger_account = (
        await db.exec(select(Account).where(Account.id == bank_account.ledger_account_id))
    ).first()
    if not bank_ledger_account:
        raise ValidationError("Bank account has no linked ledger account")

    payment_entry = await post_journal_entry(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entry=JournalEntry(
            entry_date=bill.bill_date,
            memo=f"Payment for bill {bill.id}",
            source="manual",
        ),
        lines=[
            JournalLine(account_id=ap_account.id, debit=bill.amount, credit=0),
            JournalLine(account_id=bank_ledger_account.id, debit=0, credit=bill.amount),
        ],
    )

    bill.is_paid = True
    db.add(bill)

    await record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="bill",
        entity_id=bill.id,
        action="pay",
        diff_json=f'{{"payment_journal_entry_id": "{payment_entry.id}", "bank_account_id": "{bank_account_id}"}}',
    )

    await db.commit()
    await db.refresh(bill)
    return bill