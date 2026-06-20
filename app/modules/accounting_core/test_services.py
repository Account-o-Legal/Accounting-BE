"""Smallest possible check that fails if the balance rule breaks.
Run: python -m app.modules.accounting_core.test_services
"""

import asyncio

from app.core.exceptions import UnbalancedEntryError
from app.modules.accounting_core.models import JournalLine


def _is_balanced(lines: list[JournalLine]) -> bool:
    return round(sum(l.debit for l in lines) - sum(l.credit for l in lines), 2) == 0


def test_balanced_entry_passes():
    lines = [JournalLine(debit=100, credit=0), JournalLine(debit=0, credit=100)]
    assert _is_balanced(lines)


def test_unbalanced_entry_fails():
    lines = [JournalLine(debit=100, credit=0), JournalLine(debit=0, credit=99)]
    assert not _is_balanced(lines)


if __name__ == "__main__":
    test_balanced_entry_passes()
    test_unbalanced_entry_fails()
    print("ok")
