"""Tests the audit read path: owner/admin-only access (the actual
security boundary being added), entity filtering, and tenant isolation
(workspace A's audit log must never leak into workspace B's query).

Run: python -m app.modules.audit.test_audit_events
"""

import asyncio

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.audit import list_audit_events, record_audit_event
from app.dependencies import require_workspace_admin
from app.modules.auth.models import WorkspaceMember

TENANT_A = "ws_audit_test_a"
TENANT_B = "ws_audit_test_b"


async def _make_test_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _run_owner_can_access_admin_endpoint() -> None:
    session_factory = await _make_test_session_factory()
    async with session_factory() as db:
        db.add(WorkspaceMember(user_id="user1", workspace_id=TENANT_A, role="owner"))
        await db.commit()

    async with session_factory() as db:
        result = await require_workspace_admin(
            workspace=TENANT_A, user={"sub": "user1"}, db=db
        )
    assert result == TENANT_A


async def _run_viewer_is_rejected_from_admin_endpoint() -> None:
    """The actual security boundary: a viewer-role member is a real
    member of the workspace (would pass get_active_workspace fine) but
    must NOT pass require_workspace_admin."""
    session_factory = await _make_test_session_factory()
    async with session_factory() as db:
        db.add(WorkspaceMember(user_id="user2", workspace_id=TENANT_A, role="viewer"))
        await db.commit()

    async with session_factory() as db:
        raised = False
        try:
            await require_workspace_admin(workspace=TENANT_A, user={"sub": "user2"}, db=db)
        except HTTPException as exc:
            raised = True
            assert exc.status_code == 403
        assert raised, "expected a viewer to be rejected from an admin-only endpoint"


async def _run_role_is_checked_per_workspace_not_from_jwt() -> None:
    """The exact bug this dependency exists to prevent: a user who is
    owner on Workspace A but viewer on Workspace B must be rejected when
    accessing Workspace B's audit log, even if a stale JWT field said
    role=owner (from logging in with Workspace A first)."""
    session_factory = await _make_test_session_factory()
    async with session_factory() as db:
        db.add(WorkspaceMember(user_id="user3", workspace_id=TENANT_A, role="owner"))
        db.add(WorkspaceMember(user_id="user3", workspace_id=TENANT_B, role="viewer"))
        await db.commit()

    async with session_factory() as db:
        # Stale/misleading JWT claim — role="owner" is irrelevant here;
        # require_workspace_admin must re-check against TENANT_B specifically.
        raised = False
        try:
            await require_workspace_admin(
                workspace=TENANT_B, user={"sub": "user3", "role": "owner"}, db=db
            )
        except HTTPException as exc:
            raised = True
            assert exc.status_code == 403
        assert raised, "JWT's stale role field must not override the real per-workspace role"


async def _run_audit_events_filter_by_entity_and_stay_tenant_scoped() -> None:
    session_factory = await _make_test_session_factory()
    async with session_factory() as db:
        await record_audit_event(
            db, tenant_id=TENANT_A, actor_user_id="user1",
            entity_type="invoice", entity_id="inv1", action="create", diff_json="{}",
        )
        await record_audit_event(
            db, tenant_id=TENANT_A, actor_user_id="user1",
            entity_type="invoice", entity_id="inv2", action="create", diff_json="{}",
        )
        await record_audit_event(
            db, tenant_id=TENANT_B, actor_user_id="user3",
            entity_type="invoice", entity_id="inv1", action="create", diff_json="{}",
        )
        await db.commit()

    async with session_factory() as db:
        # Filtered to one specific entity within tenant A.
        events = await list_audit_events(
            db, tenant_id=TENANT_A, entity_type="invoice", entity_id="inv1"
        )
    assert len(events) == 1
    assert events[0].entity_id == "inv1"
    assert events[0].tenant_id == TENANT_A

    async with session_factory() as db:
        # Unfiltered, tenant A only — must not include tenant B's inv1 event.
        all_a_events = await list_audit_events(db, tenant_id=TENANT_A)
    assert len(all_a_events) == 2
    assert all(e.tenant_id == TENANT_A for e in all_a_events)


def test_owner_can_access_admin_endpoint():
    asyncio.run(_run_owner_can_access_admin_endpoint())


def test_viewer_is_rejected_from_admin_endpoint():
    asyncio.run(_run_viewer_is_rejected_from_admin_endpoint())


def test_role_is_checked_per_workspace_not_from_jwt():
    asyncio.run(_run_role_is_checked_per_workspace_not_from_jwt())


def test_audit_events_filter_by_entity_and_stay_tenant_scoped():
    asyncio.run(_run_audit_events_filter_by_entity_and_stay_tenant_scoped())


if __name__ == "__main__":
    test_owner_can_access_admin_endpoint()
    test_viewer_is_rejected_from_admin_endpoint()
    test_role_is_checked_per_workspace_not_from_jwt()
    test_audit_events_filter_by_entity_and_stay_tenant_scoped()
    print("ok")