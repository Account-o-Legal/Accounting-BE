"""Checks the pure-logic part of seed.py: jurisdiction pack -> Account
objects and TaxRate objects, and the lookup helper used right after
seeding. Doesn't touch a DB — db.add()/db.flush() are tested in the
integration tests; these are the tripwires for the jurisdiction pack
itself being correct.

Run: python -m app.modules.accounting_core.test_seed
"""

from app.core.config import load_jurisdiction
from app.modules.accounting_core.models import Account
from app.modules.accounting_core.seed import find_account_by_code


def test_pk_jurisdiction_has_bank_account_code():
    """approve_transaction and auth/router.py hardcode code '1020' —
    if this ever stops existing in pk.json, the seeding silently skips
    creating a default BankAccount. This test is the tripwire."""
    pack = load_jurisdiction("pk")
    codes = [entry["code"] for entry in pack["default_chart_of_accounts"]]
    assert "1020" in codes


def test_pk_jurisdiction_has_accounts_receivable():
    """sales/services.py hardcodes code '1200' for AR posting."""
    pack = load_jurisdiction("pk")
    codes = [entry["code"] for entry in pack["default_chart_of_accounts"]]
    assert "1200" in codes


def test_pk_jurisdiction_has_accounts_payable():
    """purchases/services.py hardcodes code '2010' for AP posting."""
    pack = load_jurisdiction("pk")
    codes = [entry["code"] for entry in pack["default_chart_of_accounts"]]
    assert "2010" in codes


def test_pk_jurisdiction_has_gst_payable():
    """sales/services.py hardcodes code '2200' for GST posting."""
    pack = load_jurisdiction("pk")
    codes = [entry["code"] for entry in pack["default_chart_of_accounts"]]
    assert "2200" in codes


def test_pk_jurisdiction_has_default_tax_rates():
    """seed_tax_rates reads default_tax_rates from pk.json — if this key
    is missing or empty, new workspaces get no tax rates and every
    GST-bearing invoice creation fails with a ValidationError."""
    pack = load_jurisdiction("pk")
    rates = pack.get("default_tax_rates", [])
    assert len(rates) > 0, "pk.json must define at least one default_tax_rates entry"
    names = [r["name"] for r in rates]
    assert any("17" in name for name in names), "expected a GST 17% rate in pk.json"


def test_pk_jurisdiction_has_exactly_one_default_tax_rate():
    """Multiple is_default=true rates would make 'apply default GST'
    ambiguous — enforce exactly one."""
    pack = load_jurisdiction("pk")
    defaults = [r for r in pack.get("default_tax_rates", []) if r.get("is_default")]
    assert len(defaults) == 1, f"expected exactly one default tax rate, got {len(defaults)}"


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
    test_pk_jurisdiction_has_accounts_receivable()
    test_pk_jurisdiction_has_accounts_payable()
    test_pk_jurisdiction_has_gst_payable()
    test_pk_jurisdiction_has_default_tax_rates()
    test_pk_jurisdiction_has_exactly_one_default_tax_rate()
    test_find_account_by_code_returns_match()
    test_find_account_by_code_returns_none_when_missing()
    print("ok")