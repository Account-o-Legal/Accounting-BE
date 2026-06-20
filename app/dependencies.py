"""Shared Depends() used across every module router.

The one non-obvious piece here is `get_active_workspace`: since multi-client
workspace switching is the MVP's whole pitch, every authenticated request
must resolve which client's books it's operating on, not just who the user
is. The JWT carries the user; the `X-Workspace-Id` header (set by the
frontend's workspace switcher) carries the "which client" part.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException
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


CurrentUser = Annotated[dict, Depends(get_current_user)]
ActiveWorkspace = Annotated[str, Depends(get_active_workspace)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
