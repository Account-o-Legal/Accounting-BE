from datetime import date

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
    status: InvoiceStatus = Field(default=InvoiceStatus.DRAFT)
    # ponytail: currency is a fixed field, not an FX module — MVP scope is
    # single-currency (PKR). Multi-currency conversion logic deferred to V2;
    # adding the column now avoids a painful migration later.
    currency: str = Field(default="PKR")


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


class InvoiceCreate(SQLModel):
    customer_id: str
    issue_date: date
    due_date: date
    lines: list[InvoiceLineCreate]
