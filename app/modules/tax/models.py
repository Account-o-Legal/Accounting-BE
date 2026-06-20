"""Tax rates + transactions. Audit logging used to live here in the
original tree — moved to core/audit.py since every module's mutations
need it, not just tax's."""

from sqlmodel import Field, SQLModel

from app.db.mixins import TenantMixin, ULIDMixin


class TaxRate(ULIDMixin, TenantMixin, SQLModel, table=True):
    __tablename__ = "tax_rates"

    name: str  # "GST 17%"
    rate_percent: float
    is_default: bool = Field(default=False)


class FbrFiling(ULIDMixin, TenantMixin, SQLModel, table=True):
    """One row per filing period submission. ponytail: actual FBR API
    integration (IRIS web services) is a real, fiddly piece of work —
    scaffolded as a single service function stub, not built out, until
    FBR's sandbox credentials are in hand."""

    __tablename__ = "fbr_filings"

    period_start: str
    period_end: str
    status: str = Field(default="draft")
