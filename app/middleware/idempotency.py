"""Dedupe POST/PUT requests by Idempotency-Key header, scoped per tenant.
Critical for the ledger: a retried "create invoice" request must not
double-post. Redis SET NX with a short TTL is the entire mechanism.

ponytail: stores the response body in Redis on first success, replays it
verbatim on a duplicate key. No distributed lock beyond Redis's own
atomicity — fine at MVP request volume, revisit if double-submits under
concurrent retries show up in practice (unlikely: NX is atomic).
"""

import json

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

_redis = Redis.from_url(settings.redis_url)
TTL_SECONDS = 60 * 60 * 24


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        key = request.headers.get("idempotency-key")
        if request.method not in ("POST", "PUT") or not key:
            return await call_next(request)

        cache_key = f"idem:{request.state.__dict__.get('tenant_id', 'none')}:{key}"
        cached = await _redis.get(cache_key)
        if cached:
            return JSONResponse(content=json.loads(cached))

        response = await call_next(request)
        if response.status_code < 400:
            body = b"".join([chunk async for chunk in response.body_iterator])
            await _redis.set(cache_key, body, ex=TTL_SECONDS)
            return Response(content=body, status_code=response.status_code, headers=dict(response.headers))
        return response
