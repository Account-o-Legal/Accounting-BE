"""ARQ worker config. ponytail: 2 queues for MVP (import, report) instead
of the original 5 (+notification, +anomaly). notification_worker and
anomaly_worker get created when notifications and anomaly detection
actually ship (V1.5 / V2) — empty queue handlers aren't infrastructure,
they're just files nobody runs yet."""

from arq.connections import RedisSettings

from app.core.config import settings
from app.workers.import_worker import process_bank_statement
from app.workers.report_worker import generate_report


class WorkerSettings:
    functions = [process_bank_statement, generate_report]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)


# Importable handle for routers to enqueue jobs against, e.g.
# `from app.workers.main import import_queue`
import_queue = WorkerSettings
