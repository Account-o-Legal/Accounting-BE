"""Narrow AI categorization. The entire design constraint, repeated because
it matters more than any code here: SUGGEST ONLY, NEVER AUTO-POST.

Pipeline: rule match (cheap, instant, ~80% of txns) -> if no rule fires,
LLM fallback (costs money, only hit on the ambiguous ~20%) -> always lands
in the review queue as a suggestion, never directly as a posted entry.

ponytail: this is ONE file, not a five-file 'ai/' subsystem (gateway,
explainability, anomaly, coaching) — those V2/V3 capabilities don't exist
yet, so they don't get files yet either.
"""

import json

from anthropic import AsyncAnthropic

from app.core.config import settings
from app.modules.banking.models import BankTransaction

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)


def try_rule_match(description: str, vendor_rules: dict[str, str]) -> str | None:
    """Cheapest possible categorization: exact/substring match against
    vendor name -> account_id rules the tenant has built up from past
    approvals. This is what makes the system 'learn' over time without
    any ML — every approval in the review queue should feed back into
    this rules table (wiring that feedback loop is a V2 polish item, the
    table itself is MVP)."""
    description_lower = description.lower()
    for vendor_pattern, account_id in vendor_rules.items():
        if vendor_pattern.lower() in description_lower:
            return account_id
    return None


async def suggest_category_via_llm(description: str, amount: float, chart_of_accounts: list[dict]) -> dict:
    """Fallback only — called for the minority of transactions no rule
    matches. Returns a suggestion + confidence, never writes to the ledger
    directly; the caller (import_worker) is responsible for landing this
    as a 'needs_review' or 'ai_suggested' row, not a posted entry.
    """
    accounts_list = "\n".join(f"- {a['id']}: {a['name']}" for a in chart_of_accounts)
    prompt = (
        f"Transaction: \"{description}\" amount: {amount}\n"
        f"Chart of accounts:\n{accounts_list}\n\n"
        "Respond ONLY with JSON: {\"account_id\": \"...\", \"confidence\": 0.0-1.0}"
    )
    response = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    return json.loads(text)


async def categorize_transaction(
    txn: BankTransaction, vendor_rules: dict[str, str], chart_of_accounts: list[dict]
) -> BankTransaction:
    rule_match = try_rule_match(txn.description, vendor_rules)
    if rule_match:
        txn.suggested_account_id = rule_match
        txn.category_status = "auto"
        txn.confidence = 1.0
        return txn

    suggestion = await suggest_category_via_llm(txn.description, txn.amount, chart_of_accounts)
    txn.suggested_account_id = suggestion["account_id"]
    txn.confidence = suggestion["confidence"]
    # Still lands in the review queue even at high confidence — "suggest
    # only" is a product promise, not just a fallback-path behavior.
    txn.category_status = "ai_suggested"
    return txn
