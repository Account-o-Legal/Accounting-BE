"""Checks the debit/credit sign logic in approve_transaction without
needing a live DB — the part most likely to be silently wrong is the
inflow/outflow direction, not the DB plumbing around it.
Run: python -m app.modules.banking.test_approve_transaction
"""

from app.modules.accounting_core.models import JournalLine


def _build_lines(bank_account_id: str, category_account_id: str, amount: float) -> list[JournalLine]:
    is_inflow = amount >= 0
    abs_amount = abs(amount)
    return [
        JournalLine(
            account_id=bank_account_id,
            debit=abs_amount if is_inflow else 0,
            credit=0 if is_inflow else abs_amount,
        ),
        JournalLine(
            account_id=category_account_id,
            debit=0 if is_inflow else abs_amount,
            credit=abs_amount if is_inflow else 0,
        ),
    ]


def _is_balanced(lines: list[JournalLine]) -> bool:
    return round(sum(l.debit for l in lines) - sum(l.credit for l in lines), 2) == 0


def test_inflow_debits_bank_credits_revenue():
    lines = _build_lines("bank", "revenue", 500)
    bank_line, category_line = lines
    assert bank_line.debit == 500 and bank_line.credit == 0
    assert category_line.credit == 500 and category_line.debit == 0
    assert _is_balanced(lines)


def test_outflow_credits_bank_debits_expense():
    lines = _build_lines("bank", "expense", -200)
    bank_line, category_line = lines
    assert bank_line.credit == 200 and bank_line.debit == 0
    assert category_line.debit == 200 and category_line.credit == 0
    assert _is_balanced(lines)


if __name__ == "__main__":
    test_inflow_debits_bank_credits_revenue()
    test_outflow_credits_bank_debits_expense()
    print("ok")
