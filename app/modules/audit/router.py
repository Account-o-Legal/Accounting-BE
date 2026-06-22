"""Read-only audit trail endpoint. Owner/admin only — see
require_workspace_admin's docstring for why this can't just check the
JWT's role field. Write-side logic (record_audit_event) lives in
core/audit.py since every module's mutations call it directly; this
router is purely the view onto that data.
"""

from fastapi import APIRouter

from app.core.audit import list_audit_events
from app.dependencies import AdminWorkspace, DbSession

router = APIRouter()


@router.get("/events")
async def get_audit_events(
    workspace: AdminWorkspace,
    db: DbSession,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 100,
):
    """List recent audit events for this workspace, optionally filtered
    to one entity's full history (e.g. entity_type=invoice&entity_id=...
    shows everything that happened to one specific invoice).
    """
    events = await list_audit_events(
        db,
        tenant_id=workspace,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )
    return events