"""Mixins every table gets. TenantMixin is the multi-tenancy enforcement
point: every business table carries tenant_id, and every query in every
module must filter by it (enforced via the repository layer, not trusted
to be remembered per-query).

ponytail: switched from raw SQLAlchemy declarative to SQLModel — one class
now serves as both the ORM model and the Pydantic schema, so routers no
longer need a parallel `XCreate`/`XRead` class hand-kept in sync with the
table. See sales/models.py for the pattern.
"""

from datetime import datetime, timezone

from sqlmodel import Field
from ulid import ULID


def _new_ulid() -> str:
    return str(ULID())


class ULIDMixin:
    id: str = Field(default_factory=_new_ulid, primary_key=True, max_length=26)


class TenantMixin:
    # tenant_id == workspace_id == the "client" the accountant is viewing
    tenant_id: str = Field(index=True, max_length=26)


class TimestampMixin:
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )
