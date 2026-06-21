"""ARQ worker config. ponytail: 2 queues for MVP (import, report) instead
of the original 5 (+notification, +anomaly). notification_worker and
anomaly_worker get created when notifications and anomaly detection
actually ship (V1.5 / V2) — empty queue handlers aren't infrastructure,
they're just files nobody runs yet."""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings
from app.workers.import_worker import process_bank_statement
from app.workers.report_worker import generate_report


class WorkerSettings:
    functions = [process_bank_statement, generate_report]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)


class _LazyArqPool:
    """Routers call `await import_queue.enqueue_job(...)` on this. The
    real ArqRedis connection is opened on first use, not at import time —
    routers shouldn't pay a Redis-connection cost just for importing this
    module (see the ponytail note in banking/router.py's lazy import).

    ponytail: one pool shared by every enqueue caller in the process,
    not a connection-per-request. ARQ's pool is built on redis-py's
    connection pool internally, so this is the same pattern arq's own
    docs recommend — no extra pooling layer needed here.
    """

    def __init__(self, redis_settings: RedisSettings):
        self._redis_settings = redis_settings
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(self._redis_settings)
        return self._pool

    async def enqueue_job(self, *args, **kwargs):
        pool = await self._get_pool()
        return await pool.enqueue_job(*args, **kwargs)


# Importable handle for routers to enqueue jobs against, e.g.
# `from app.workers.main import import_queue`
import_queue = _LazyArqPool(WorkerSettings.redis_settings)