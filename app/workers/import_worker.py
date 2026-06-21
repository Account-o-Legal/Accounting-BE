"""Bank statement processing — the async job behind POST /banking/import.
This is where rules-first + LLM-fallback categorization actually runs,
off the request thread, so a 500-row CSV doesn't block an HTTP response.
"""

import csv
from datetime import datetime
from decimal import Decimal
from io import StringIO

from sqlmodel import select

from app.db.session import async_session
from app.modules.accounting_core.models import Account
from app.modules.ai.services import categorize_transaction
from app.modules.banking.models import BankAccount, BankTransaction
from app.modules.banking.rules import VendorRule


async def process_bank_statement(ctx, workspace_id: str, file_bytes: bytes) -> dict:
    # ponytail: CSV/OFX parsing uses `csv` stdlib + a couple of known bank
    # column-mapping presets — not a generic-format-detection engine.
    # Add format auto-detection only once real customer files reveal which
    # bank formats actually show up.
    rows = _parse_csv(file_bytes)

    async with async_session() as db:
        vendor_rules = await _load_vendor_rules(db, workspace_id)
        chart_of_accounts = await _load_chart_of_accounts(db, workspace_id)

        default_bank_account = (
            await db.exec(
                select(BankAccount).where(
                    BankAccount.tenant_id == workspace_id
                )
            )
        ).first()

        if not default_bank_account:
            raise ValueError(
                "Workspace has no bank account configured"
            )

        created = 0

        for row in rows:
            txn = BankTransaction(
                tenant_id=workspace_id,
                bank_account_id=default_bank_account.id,
                txn_date=row["date"],
                description=row["description"],
                amount=row["amount"],
            )

            txn = await categorize_transaction(
                txn,
                vendor_rules,
                chart_of_accounts,
            )

            db.add(txn)
            created += 1

        await db.commit()

    return {"imported": created}


def _parse_csv(file_bytes: bytes) -> list[dict]:
    """
    MVP format:

    Date,Description,Amount
    2026-06-01,K-Electric,-25000
    2026-06-02,Client Payment,150000
    """

    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))

    rows: list[dict] = []

    for row in reader:
        rows.append(
            {
                "date": datetime.strptime(
                    row["Date"].strip(),
                    "%Y-%m-%d",
                ).date(),
                "description": row["Description"].strip(),
                "amount": float(
                    Decimal(
                        row["Amount"]
                        .replace(",", "")
                        .strip()
                    )
                ),
            }
        )

    return rows


async def _load_chart_of_accounts(db, workspace_id: str) -> list[dict]:
    result = await db.exec(
        select(Account).where(
            Account.tenant_id == workspace_id
        )
    )

    return [
        {
            "id": account.id,
            "name": account.name,
            "code": account.code,
            "type": account.type,
        }
        for account in result.all()
    ]


async def _load_vendor_rules(db, workspace_id: str) -> dict[str, str]:
    """
    Returns:

    {
        "k-electric": "<account_id>",
        "ptcl": "<account_id>",
    }
    """

    result = await db.exec(
        select(VendorRule).where(
            VendorRule.tenant_id == workspace_id
        )
    )

    rules: dict[str, str] = {}

    for rule in result.all():
        rules[rule.vendor_pattern.lower()] = rule.account_id

    return rules