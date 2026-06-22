"""Tests the duplicate-email registration path returns a clean 409
(ConflictError), not a raw 500 IntegrityError traceback — the actual bug
this fixes. A new accountant signing up with an email already in the
system should get an honest, actionable error, not a stack trace.

Run: python -m app.modules.auth.test_register_conflict
"""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import ConflictError
from app.modules.auth.models import RegisterRequest
from app.modules.auth.router import register

# Every model module touched by register() needs to be imported so
# SQLModel.metadata knows about their tables before create_all runs —
# same requirement as every other in-memory-SQLite test in this codebase.
import app.modules.accounting_core.models  # noqa: F401
import app.modules.banking.models  # noqa: F401
import app.core.audit  # noqa: F401


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _run_duplicate_email_returns_conflict_not_500() -> None:
    session_factory = await _make_test_session_factory()

    async with session_factory() as db:
        await register(
            RegisterRequest(
                email="dup@example.com", password="testpass123", workspace_name="First Co"
            ),
            db,
        )

    async with session_factory() as db:
        raised = False
        try:
            await register(
                RegisterRequest(
                    email="dup@example.com", password="anotherpass", workspace_name="Second Co"
                ),
                db,
            )
        except ConflictError as exc:
            raised = True
            assert exc.status_code == 409
            assert "already exists" in exc.message
        assert raised, "expected ConflictError, not a raw IntegrityError/500"


def test_duplicate_email_returns_conflict_not_500():
    asyncio.run(_run_duplicate_email_returns_conflict_not_500())


if __name__ == "__main__":
    test_duplicate_email_returns_conflict_not_500()
    print("ok")