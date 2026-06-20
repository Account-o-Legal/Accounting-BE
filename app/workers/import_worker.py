"""Bank statement processing — the async job behind POST /banking/import.
This is where rules-first + LLM-fallback categorization actually runs,
off the request thread, so a 500-row CSV doesn't block an HTTP response.
"""

from app.db.session import async_session
from app.modules.ai.services import categorize_transaction
from app.modules.banking.models import BankTransaction


async def process_bank_statement(ctx, workspace_id: str, file_bytes: bytes) -> dict:
    # ponytail: CSV/OFX parsing uses `csv` stdlib + a couple of known bank
    # column-mapping presets — not a generic-format-detection engine.
    # Add format auto-detection only once real customer files reveal which
    # bank formats actually show up.
    rows = _parse_csv(file_bytes)

    async with async_session() as db:
        vendor_rules = await _load_vendor_rules(db, workspace_id)
        chart_of_accounts = await _load_chart_of_accounts(db, workspace_id)

        created = 0
        for row in rows:
            txn = BankTransaction(
                tenant_id=workspace_id,
                bank_account_id=row["account_id"],
                txn_date=row["date"],
                description=row["description"],
                amount=row["amount"],
            )
            txn = await categorize_transaction(txn, vendor_rules, chart_of_accounts)
            db.add(txn)
            created += 1
        await db.commit()

    return {"imported": created}


def _parse_csv(file_bytes: bytes) -> list[dict]:
    raise NotImplementedError  # scaffold


async def _load_vendor_rules(db, workspace_id: str) -> dict[str, str]:
    raise NotImplementedError  # scaffold


async def _load_chart_of_accounts(db, workspace_id: str) -> list[dict]:
    raise NotImplementedError  # scaffold
