"""Stamps request.state.tenant_id from the X-Workspace-Id header so any
code deep in a call stack (loggers, repositories) can access "which client"
without threading it through every function signature.

Actual authorization (is this user really a member of this workspace?)
happens in app.dependencies.get_active_workspace — this middleware only
makes the value available, it does not trust it.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.tenant_id = request.headers.get("x-workspace-id")
        return await call_next(request)
