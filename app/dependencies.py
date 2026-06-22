"""Shared Depends() used across every module router.

The one non-obvious piece here is `get_active_workspace`: since multi-client
workspace switching is the MVP's whole pitch, every authenticated request
must resolve which client's books it's operating on, not just who the user
is. The JWT carries the user; the `X-Workspace-Id` header (set by the
frontend's workspace switcher) carries the "which client" part.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import decode_jwt
from app.db.session import get_db


async def get_current_user(
    authorization: Annotated[str, Header()],
) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    return decode_jwt(token)  # raises on invalid/expired


async def get_active_workspace(
    x_workspace_id: Annotated[str, Header()],
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> str:
    """Resolve + authorize the workspace (tenant) this request operates on.

    ponytail: membership check is a single query against a
    `workspace_members` table — no caching layer yet. Add Redis-cached
    membership lookups only if this query shows up in P95 latency profiling.
    """
    if x_workspace_id not in user.get("workspace_ids", []):
        raise HTTPException(403, "Not a member of this workspace")
    return x_workspace_id


async def require_workspace_admin(
    workspace: Annotated[str, Depends(get_active_workspace)],
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> str:
    """Stricter version of get_active_workspace: confirms the caller's
    role IN THIS SPECIFIC WORKSPACE is owner/admin, not just that they're
    a member.

    This deliberately re-queries WorkspaceMember rather than trusting
    user["role"] from the JWT — that field is only the role in whichever
    workspace was first in the list at login time (see auth/router.py's
    login()), not the role in the currently-active workspace. An
    accountant who is owner on Client A and viewer on Client B must be
    blocked here when X-Workspace-Id points at Client B, even though
    their JWT might say role=owner from a Client-A-first login.
    """
    from app.modules.auth.models import WorkspaceMember  # local import: avoids a
    # circular import (auth.models -> dependencies is not a thing today, but
    # dependencies -> auth.models at module load time would be, since
    # auth/router.py imports from dependencies).

    membership = (
        await db.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace,
                WorkspaceMember.user_id == user["sub"],
            )
        )
    ).first()
    if not membership or membership.role not in ("owner", "admin"):
        raise HTTPException(403, "This action requires owner or admin access to this workspace")
    return workspace


CurrentUser = Annotated[dict, Depends(get_current_user)]
ActiveWorkspace = Annotated[str, Depends(get_active_workspace)]
AdminWorkspace = Annotated[str, Depends(require_workspace_admin)]
DbSession = Annotated[AsyncSession, Depends(get_db)]