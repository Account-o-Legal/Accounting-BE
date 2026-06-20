from datetime import date

from sqlmodel import Field, SQLModel

from app.db.mixins import TenantMixin, TimestampMixin, ULIDMixin


class Vendor(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "vendors"

    name: str
    email: str | None = None


class Bill(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    """A vendor bill. receipt_file_id links to files module — receipt
    image is what the AI categorization fallback reads when rules don't
    match (see ai/services.py)."""

    __tablename__ = "bills"

    vendor_id: str = Field(foreign_key="vendors.id", index=True)
    bill_date: date
    amount: float = Field(max_digits=18, decimal_places=2)
    receipt_file_id: str | None = None
    is_paid: bool = Field(default=False)


class BillCreate(SQLModel):
    vendor_id: str
    bill_date: date
    amount: float
    receipt_file_id: str | None = None
