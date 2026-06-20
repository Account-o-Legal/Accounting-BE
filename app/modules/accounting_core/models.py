"""Double-entry ledger. The non-negotiable rule enforced here: every
JournalEntry's lines must sum debits == credits, checked in the service
layer before commit, never trusted to the caller.

SQLModel note: each class below is BOTH the DB table (table=True) and the
API schema. Where an endpoint needs a narrower shape (e.g. "create" doesn't
take an id), we subclass without table=True instead of hand-writing a
parallel Pydantic model — see JournalEntryCreate at the bottom.
"""

from datetime import date

from sqlmodel import Field, SQLModel

from app.core.enums import JournalEntryStatus
from app.db.mixins import TenantMixin, TimestampMixin, ULIDMixin


class Account(ULIDMixin, TenantMixin, SQLModel, table=True):
    """Chart of Accounts entry. type drives report placement (P&L vs
    Balance Sheet) — see reporting module."""

    __tablename__ = "accounts"

    code: str  # e.g. "1010"
    name: str
    type: str  # asset | liability | equity | revenue | expense
    parent_id: str | None = Field(default=None, foreign_key="accounts.id")


class JournalEntry(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "journal_entries"

    entry_date: date
    memo: str | None = None
    status: JournalEntryStatus = Field(default=JournalEntryStatus.DRAFT)
    # source distinguishes AI-suggested vs manually entered — feeds the
    # "approve AI suggestion" review queue UX and the confidence metric.
    source: str = Field(default="manual")  # manual | ai_suggested | import


class JournalLine(ULIDMixin, SQLModel, table=True):
    __tablename__ = "journal_lines"

    journal_entry_id: str = Field(foreign_key="journal_entries.id", index=True)
    account_id: str = Field(foreign_key="accounts.id", index=True)
    debit: float = Field(default=0, max_digits=18, decimal_places=2)
    credit: float = Field(default=0, max_digits=18, decimal_places=2)


class AccountingPeriod(ULIDMixin, TenantMixin, SQLModel, table=True):
    __tablename__ = "accounting_periods"

    start_date: date
    end_date: date
    is_closed: bool = Field(default=False)


# --- Request/response shapes, derived from the table models, not duplicated ---

class JournalLineCreate(SQLModel):
    account_id: str
    debit: float = 0
    credit: float = 0


class JournalEntryCreate(SQLModel):
    entry_date: date
    memo: str | None = None
    lines: list[JournalLineCreate]
