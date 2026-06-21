"""Narrow AI categorization. The entire design constraint, repeated because
it matters more than any code here: SUGGEST ONLY, NEVER AUTO-POST.

MVP mode:
- Rule-based categorization only.
- No LLM calls.
- Unknown transactions go to needs_review.

The Anthropic fallback remains in the file but is disabled/commented out
until we have enough real customer data to justify the cost/complexity.
"""

import json

# Phase 2 (disabled for MVP)
# from anthropic import AsyncAnthropic

from app.core.config import settings
from app.modules.banking.models import BankTransaction

# Phase 2 (disabled for MVP)
# _client = AsyncAnthropic(api_key=settings.anthropic_api_key)


def try_rule_match(description: str, vendor_rules: dict[str, str]) -> str | None:
    """Cheapest possible categorization: exact/substring match against
    vendor name -> account_id rules the tenant has built up from past
    approvals.
    """
    description_lower = description.lower()

    for vendor_pattern, account_id in vendor_rules.items():
        if vendor_pattern.lower() in description_lower:
            return account_id

    return None


# ---------------------------------------------------------------------
# Phase 2: LLM fallback (disabled for MVP)
# ---------------------------------------------------------------------
#
# async def suggest_category_via_llm(
#     description: str,
#     amount: float,
#     chart_of_accounts: list[dict],
# ) -> dict:
#     accounts_list = "\n".join(
#         f"- {a['id']}: {a['name']}"
#         for a in chart_of_accounts
#     )
#
#     prompt = (
#         f'Transaction: "{description}" amount: {amount}\n'
#         f"Chart of accounts:\n{accounts_list}\n\n"
#         'Respond ONLY with JSON: {"account_id": "...", "confidence": 0.0-1.0}'
#     )
#
#     response = await _client.messages.create(
#         model="claude-sonnet-4-6",
#         max_tokens=100,
#         messages=[
#             {
#                 "role": "user",
#                 "content": prompt,
#             }
#         ],
#     )
#
#     text = response.content[0].text.strip()
#     return json.loads(text)
#
# ---------------------------------------------------------------------


async def categorize_transaction(
    txn: BankTransaction,
    vendor_rules: dict[str, str],
    chart_of_accounts: list[dict],
) -> BankTransaction:
    """
    MVP behavior:

    Rule hit:
        auto + suggested account

    Rule miss:
        needs_review

    No LLM calls.
    """

    rule_match = try_rule_match(
        txn.description,
        vendor_rules,
    )

    if rule_match:
        txn.suggested_account_id = rule_match
        txn.category_status = "auto"
        txn.confidence = 1.0
        return txn

    # MVP:
    # Unknown transactions simply enter the review queue.
    # This is safer than guessing and keeps the bookkeeping correct.

    txn.category_status = "needs_review"
    txn.confidence = None

    return txn