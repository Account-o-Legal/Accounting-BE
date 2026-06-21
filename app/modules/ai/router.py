"""ponytail: MVP AI surface area is exactly two things — categorization
(services.py) and explaining a suggestion (this endpoint). Anomaly
detection and cash-flow coaching are V2/V3; no router stubs for them here
since an empty endpoint that 404s isn't more honest than no endpoint."""

from fastapi import APIRouter
from sqlmodel import select

from app.core.exceptions import NotFoundError
from app.dependencies import ActiveWorkspace, DbSession
from app.modules.accounting_core.models import Account
from app.modules.banking.models import BankTransaction
from app.modules.banking.rules import VendorRule

router = APIRouter()


@router.get("/transactions/{txn_id}/explain")
async def explain_suggestion(txn_id: str, workspace: ActiveWorkspace, db: DbSession):
    """Powers the 'why did you suggest this?' tap in the review queue —
    trust-building UI for a buyer (accountant) who won't approve a
    categorization they don't understand.

    Looks at what's actually on the transaction rather than returning a
    canned string: if a VendorRule exists matching this transaction's
    description, that's the real reason (a rule hit); otherwise it names
    whatever category_status the transaction landed in (ai_suggested or
    needs_review) honestly, instead of inventing a rule that didn't fire.
    """
    txn = (
        await db.exec(
            select(BankTransaction).where(
                BankTransaction.id == txn_id, BankTransaction.tenant_id == workspace
            )
        )
    ).first()
    if not txn:
        raise NotFoundError("Transaction not found")

    if not txn.suggested_account_id:
        return {
            "txn_id": txn_id,
            "explanation": "No category has been suggested for this transaction yet.",
        }

    account = (
        await db.exec(select(Account).where(Account.id == txn.suggested_account_id))
    ).first()
    account_name = account.name if account else txn.suggested_account_id

    vendor_pattern = txn.description.strip().lower()
    matched_rule = (
        await db.exec(
            select(VendorRule).where(
                VendorRule.tenant_id == workspace,
                VendorRule.vendor_pattern == vendor_pattern,
            )
        )
    ).first()

    if matched_rule and matched_rule.account_id == txn.suggested_account_id:
        explanation = (
            f"Matched vendor rule: \"{matched_rule.vendor_pattern}\" -> {account_name}. "
            "This rule was created from a past approval of the same vendor."
        )
    elif txn.category_status == "ai_suggested":
        explanation = (
            f"No existing rule matched this vendor, so this category ({account_name}) "
            f"was suggested by AI, with confidence {txn.confidence:.0%}." if txn.confidence is not None
            else f"No existing rule matched this vendor, so this category ({account_name}) was AI-suggested."
        )
    else:
        explanation = f"Category set to {account_name}."

    return {"txn_id": txn_id, "explanation": explanation}