from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    BOOKKEEPER = "bookkeeper"
    VIEWER = "viewer"


class JournalEntryStatus(StrEnum):
    DRAFT = "draft"        # AI-suggested, awaiting human approval
    POSTED = "posted"      # approved, hit the ledger
    VOID = "void"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"
