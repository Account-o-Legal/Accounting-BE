"""Async report generation — the job behind a future POST /reports/export
endpoint (not yet wired into reporting/router.py; that endpoint doesn't
exist yet, only the synchronous /trial-balance, /profit-and-loss,
/balance-sheet GETs do, which return JSON directly and don't need a
worker at all).

ponytail: one worker function for both PDF and CSV export — they share
the same data-fetch step (call into reporting/services.py) and only
differ in the final render call. Splitting into
report_worker_pdf.py / report_worker_csv.py would just be two files
importing the same query logic.

CSV is fully implemented below (stdlib csv, zero new dependencies).
PDF is still a stub — it needs WeasyPrint, which isn't in
requirements.txt yet. Add it when an actual "download PDF" button exists
in the UI, not speculatively now.
"""

import csv
from io import StringIO

from app.db.session import async_session
from app.modules.reporting.services import (
    generate_balance_sheet,
    generate_profit_and_loss,
    generate_trial_balance,
)

_REPORT_GENERATORS = {
    "trial_balance": generate_trial_balance,
    "profit_and_loss": generate_profit_and_loss,
    "balance_sheet": generate_balance_sheet,
}


async def generate_report(ctx, workspace_id: str, report_type: str, format: str) -> dict:
    if report_type not in _REPORT_GENERATORS:
        raise ValueError(
            f"Unknown report_type '{report_type}', expected one of {list(_REPORT_GENERATORS)}"
        )
    if format not in ("csv", "pdf"):
        raise ValueError(f"Unknown format '{format}', expected 'csv' or 'pdf'")
    if format == "pdf":
        # ponytail: real PDF rendering (WeasyPrint, HTML template per
        # report_type) not implemented yet — see module docstring. Checked
        # here, before opening a DB session, so this fails fast without
        # needing live infra just to tell the caller "not built yet."
        raise NotImplementedError("PDF export not implemented yet — use format='csv'")

    async with async_session() as db:
        data = await _REPORT_GENERATORS[report_type](db, tenant_id=workspace_id)

    return {"format": "csv", "content": _render_csv(report_type, data)}


def _render_csv(report_type: str, data: dict) -> str:
    """Flattens each report's shape into a simple CSV. Each report has a
    different structure (trial_balance is one flat account list;
    profit_and_loss/balance_sheet have multiple sections), so this
    dispatches per type rather than trying to force one generic
    dict-to-CSV path that would produce a useless table for the
    sectioned reports.
    """
    buffer = StringIO()
    writer = csv.writer(buffer)

    if report_type == "trial_balance":
        writer.writerow(["code", "name", "type", "debit", "credit", "balance"])
        for account in data["accounts"]:
            writer.writerow(
                [account["code"], account["name"], account["type"], account["debit"], account["credit"], account["balance"]]
            )
        writer.writerow([])
        writer.writerow(["total", "", "", data["total_debit"], data["total_credit"], ""])

    elif report_type == "profit_and_loss":
        writer.writerow(["section", "account", "amount"])
        for line in data["revenue"]:
            writer.writerow(["revenue", line["name"], line["amount"]])
        for line in data["expenses"]:
            writer.writerow(["expense", line["name"], line["amount"]])
        writer.writerow([])
        writer.writerow(["total_revenue", "", data["total_revenue"]])
        writer.writerow(["total_expenses", "", data["total_expenses"]])
        writer.writerow(["net_income", "", data["net_income"]])

    elif report_type == "balance_sheet":
        writer.writerow(["section", "account", "amount"])
        for line in data["assets"]:
            writer.writerow(["asset", line["name"], line["amount"]])
        for line in data["liabilities"]:
            writer.writerow(["liability", line["name"], line["amount"]])
        for line in data["equity"]:
            writer.writerow(["equity", line["name"], line["amount"]])
        writer.writerow([])
        writer.writerow(["total_assets", "", data["total_assets"]])
        writer.writerow(["total_liabilities", "", data["total_liabilities"]])
        writer.writerow(["total_equity", "", data["total_equity"]])

    return buffer.getvalue()