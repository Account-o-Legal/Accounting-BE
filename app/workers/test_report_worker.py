"""Checks _render_csv against the exact dict shapes generate_trial_balance/
generate_profit_and_loss/generate_balance_sheet actually return (see
reporting/services.py and its test_trial_balance.py for where these
shapes are defined and proven correct). Pure string-formatting logic,
no DB needed.

Run: python -m app.workers.test_report_worker
"""

import asyncio

from app.workers.report_worker import _render_csv, generate_report


def test_render_csv_trial_balance_includes_totals_row():
    data = {
        "tenant_id": "ws1",
        "accounts": [
            {"account_id": "a1", "code": "1020", "name": "Bank Account", "type": "asset", "debit": 150000.0, "credit": 25000.0, "balance": 125000.0},
        ],
        "total_debit": 150000.0,
        "total_credit": 25000.0,
        "is_balanced": False,
    }
    csv_text = _render_csv("trial_balance", data)
    assert "1020,Bank Account,asset,150000.0,25000.0,125000.0" in csv_text
    assert "total,,,150000.0,25000.0," in csv_text


def test_render_csv_profit_and_loss_includes_net_income():
    data = {
        "revenue": [{"account_id": "a1", "name": "Sales Revenue", "amount": 150000.0}],
        "expenses": [{"account_id": "a2", "name": "Utilities", "amount": 25000.0}],
        "total_revenue": 150000.0,
        "total_expenses": 25000.0,
        "net_income": 125000.0,
    }
    csv_text = _render_csv("profit_and_loss", data)
    assert "revenue,Sales Revenue,150000.0" in csv_text
    assert "expense,Utilities,25000.0" in csv_text
    assert "net_income,,125000.0" in csv_text


def test_render_csv_balance_sheet_includes_all_sections():
    data = {
        "assets": [{"account_id": "a1", "name": "Bank Account", "amount": 125000.0}],
        "liabilities": [],
        "equity": [{"account_id": None, "name": "Retained Earnings (current period)", "amount": 125000.0}],
        "total_assets": 125000.0,
        "total_liabilities": 0.0,
        "total_equity": 125000.0,
    }
    csv_text = _render_csv("balance_sheet", data)
    assert "asset,Bank Account,125000.0" in csv_text
    assert "equity,Retained Earnings (current period),125000.0" in csv_text
    assert "total_assets,,125000.0" in csv_text


def test_unknown_report_type_raises():
    raised = False
    try:
        asyncio.run(generate_report(ctx={}, workspace_id="ws1", report_type="cash_flow", format="csv"))
    except ValueError as exc:
        raised = True
        assert "Unknown report_type" in str(exc)
    assert raised


def test_pdf_format_raises_not_implemented():
    """PDF rendering is a deliberate, explicit stub (see module docstring).
    generate_report checks format='pdf' before opening any DB session,
    so this is a true no-DB-needed unit test, even with a valid
    report_type."""
    raised = False
    try:
        asyncio.run(generate_report(ctx={}, workspace_id="ws1", report_type="trial_balance", format="pdf"))
    except NotImplementedError as exc:
        raised = True
        assert "csv" in str(exc).lower()
    assert raised


if __name__ == "__main__":
    test_render_csv_trial_balance_includes_totals_row()
    test_render_csv_profit_and_loss_includes_net_income()
    test_render_csv_balance_sheet_includes_all_sections()
    test_unknown_report_type_raises()
    test_pdf_format_raises_not_implemented()
    print("ok")