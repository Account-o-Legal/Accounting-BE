from datetime import date

from sqlmodel import Field, SQLModel

from app.db.mixins import TenantMixin, TimestampMixin, ULIDMixin


class BankAccount(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "bank_accounts"

    name: str
    account_number_last4: str | None = None
    # The ledger Account (type=asset) this bank account posts against.
    # Needed because approving a transaction creates a 2-line journal
    # entry: this account on one side, the categorized account on the
    # other — without this link there's no way to know the bank's side.
    ledger_account_id: str = Field(foreign_key="accounts.id")


class BankTransaction(ULIDMixin, TenantMixin, TimestampMixin, SQLModel, table=True):
    """Raw imported row. `category_status` drives the review queue UI:
    'auto' = rule matched confidently, 'ai_suggested' = LLM fallback
    proposed a category, 'needs_review' = neither, human must pick.

    This table + its status field IS the "AI does bookkeeping" feature —
    everything else is supporting infrastructure for this one queue.
    """

    __tablename__ = "bank_transactions"

    bank_account_id: str
    txn_date: date
    description: str
    amount: float = Field(max_digits=18, decimal_places=2)
    suggested_account_id: str | None = None
    category_status: str = Field(default="needs_review")
    confidence: float | None = None
    journal_entry_id: str | None = None  # set once approved+posted
