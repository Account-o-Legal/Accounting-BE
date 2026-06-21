from sqlmodel import Field, SQLModel

from app.db.mixins import TenantMixin, TimestampMixin, ULIDMixin


class VendorRule(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "vendor_rules"

    vendor_pattern: str = Field(index=True)
    account_id: str = Field(foreign_key="accounts.id")