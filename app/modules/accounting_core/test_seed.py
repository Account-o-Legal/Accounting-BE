"""Checks the pure-logic part of seed.py: jurisdiction pack -> Account
objects, and the lookup helper used right after seeding. Doesn't touch
a DB — db.add()/db.flush() in seed_chart_of_accounts are mocked out by
testing find_account_by_code directly against constructed Account objects.

Run: python -m app.modules.accounting_core.test_seed
"""

from app.core.config import load_jurisdiction
from app.modules.accounting_core.models import Account
from app.modules.accounting_core.seed import find_account_by_code


def test_pk_jurisdiction_has_bank_account_code():
    """approve_transaction's default-BankAccount wiring in auth/router.py
    hardcodes code '1020' — if this ever stops existing in pk.json, the
    seeding silently skips creating a default bank account. This test is
    the tripwire for that."""
    pack = load_jurisdiction("pk")
    codes = [entry["code"] for entry in pack["default_chart_of_accounts"]]
    assert "1020" in codes


def test_find_account_by_code_returns_match():
    accounts = [
        Account(tenant_id="t1", code="1010", name="Cash", type="asset"),
        Account(tenant_id="t1", code="1020", name="Bank Account", type="asset"),
    ]
    found = find_account_by_code(accounts, "1020")
    assert found is not None
    assert found.name == "Bank Account"


def test_find_account_by_code_returns_none_when_missing():
    accounts = [Account(tenant_id="t1", code="1010", name="Cash", type="asset")]
    assert find_account_by_code(accounts, "9999") is None


if __name__ == "__main__":
    test_pk_jurisdiction_has_bank_account_code()
    test_find_account_by_code_returns_match()
    test_find_account_by_code_returns_none_when_missing()
    print("ok")