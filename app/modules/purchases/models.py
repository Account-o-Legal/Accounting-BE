from datetime import date

from sqlmodel import Field, SQLModel

from app.db.mixins import TenantMixin, TimestampMixin, ULIDMixin


class Vendor(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "vendors"

    name: str
    email: str | None = None


class VendorCreate(SQLModel):
    name: str
    email: str | None = None


class Bill(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    """A vendor bill. receipt_file_id links to files module — receipt
    image is what the AI categorization fallback reads when rules don't
    match (see ai/services.py).

    ponytail: account_id was missing entirely before this fix — without
    it there's no way to know which expense account a bill should debit
    when posted to the ledger (unlike bank transactions, which get a
    suggested_account_id from the AI categorization pipeline, bills have
    no equivalent automated step yet, so the category has to be supplied
    explicitly at creation). journal_entry_id links to the Expense/AP
    posting created at bill creation time — see purchases/services.py.
    """

    __tablename__ = "bills"

    vendor_id: str = Field(foreign_key="vendors.id", index=True)
    bill_date: date
    amount: float = Field(max_digits=18, decimal_places=2)
    account_id: str = Field(foreign_key="accounts.id")
    receipt_file_id: str | None = None
    is_paid: bool = Field(default=False)
    journal_entry_id: str | None = None


class BillCreate(SQLModel):
    vendor_id: str
    bill_date: date
    amount: float
    account_id: str
    receipt_file_id: str | None = None