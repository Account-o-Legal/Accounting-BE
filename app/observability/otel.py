"""OpenTelemetry wiring: traces + metrics, auto-instrumented.

ponytail: tracer/metrics/logger live in one file, not three. Each piece
is 5-10 lines; splitting them into otel.py/metrics.py/tracer.py only adds
import indirection at this size. Split them back out if any single
concern (e.g. custom business metrics) grows past ~100 lines.

structlog config (the 4th file in the original tree) is also here —
it's a logger factory, not a separate subsystem.
"""

import structlog
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider

tracer = trace.get_tracer("accounting-software")
meter = metrics.get_meter("accounting-software")

# Custom metrics referenced by business logic (e.g. AI categorization hit rate)
journal_entries_posted = meter.create_counter(
    "journal_entries_posted_total", description="Journal entries posted, by source"
)
ai_categorization_confidence = meter.create_histogram(
    "ai_categorization_confidence", description="Confidence score of AI-suggested categorizations"
)

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()


def setup_observability(app: FastAPI) -> None:
    trace.set_tracer_provider(TracerProvider())
    metrics.set_meter_provider(MeterProvider())
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    # ponytail: OTLP exporter endpoint comes from standard OTEL_EXPORTER_OTLP_*
    # env vars (collector picks them up automatically) — no custom exporter
    # config code needed here.
