from datetime import date

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.core.enums import InvoiceStatus
from app.db.mixins import TenantMixin, TimestampMixin, ULIDMixin


class Customer(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "customers"

    name: str
    email: str | None = None
    phone: str | None = None


class Invoice(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "invoices"

    customer_id: str = Field(foreign_key="customers.id", index=True)
    invoice_number: str
    issue_date: date
    due_date: date
    # ponytail: sa_type=sa.String — same reasoning as JournalEntry.status
    # and WorkspaceMember.role. No CREATE TYPE in the migration for any of
    # these, so the column has to stay plain VARCHAR; Python-side validation
    # via InvoiceStatus is unaffected.
    status: InvoiceStatus = Field(default=InvoiceStatus.DRAFT, sa_type=sa.String)
    # ponytail: currency is a fixed field, not an FX module — MVP scope is
    # single-currency (PKR). Multi-currency conversion logic deferred to V2;
    # adding the column now avoids a painful migration later.
    currency: str = Field(default="PKR")
    # journal_entry_id links to the AR/Revenue/Tax posting created at
    # invoice creation time (see sales/services.py). None until posted.
    journal_entry_id: str | None = None


class InvoiceLine(ULIDMixin, SQLModel, table=True):
    __tablename__ = "invoice_lines"

    invoice_id: str = Field(foreign_key="invoices.id", index=True)
    description: str
    quantity: float = Field(default=1, max_digits=18, decimal_places=2)
    unit_price: float = Field(max_digits=18, decimal_places=2)
    tax_rate_id: str | None = Field(default=None, foreign_key="tax_rates.id")


# --- Request shapes, built from the table fields rather than duplicated ---

class InvoiceLineCreate(SQLModel):
    description: str
    quantity: float = 1
    unit_price: float
    # ponytail: this field was missing entirely before — InvoiceLine (the
    # table) has tax_rate_id, but the create schema never exposed it, so
    # there was no way to actually request GST on a line through the API.
    # Fixed alongside the ledger-posting gap, since GST posting needs it.
    tax_rate_id: str | None = None


class InvoiceCreate(SQLModel):
    customer_id: str
    issue_date: date
    due_date: date
    lines: list[InvoiceLineCreate]