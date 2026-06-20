from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.middleware.tenant import TenantMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.observability.otel import setup_observability

from app.modules.auth.router import router as auth_router
from app.modules.accounting_core.router import router as ledger_router
from app.modules.sales.router import router as sales_router
from app.modules.purchases.router import router as purchases_router
from app.modules.banking.router import router as banking_router
from app.modules.tax.router import router as tax_router
from app.modules.reporting.router import router as reporting_router
from app.modules.files.router import router as files_router
from app.modules.billing.router import router as billing_router
from app.modules.ai.router import router as ai_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_observability(app)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

register_exception_handlers(app)

# ponytail: rate limiting deferred — add SlowAPI/Redis middleware here once
# real traffic numbers exist; no point tuning limits against zero data.
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(TenantMiddleware)

app.include_router(auth_router, prefix="/v1/auth", tags=["auth"])
app.include_router(ledger_router, prefix="/v1/ledger", tags=["accounting_core"])
app.include_router(sales_router, prefix="/v1/sales", tags=["sales"])
app.include_router(purchases_router, prefix="/v1/purchases", tags=["purchases"])
app.include_router(banking_router, prefix="/v1/banking", tags=["banking"])
app.include_router(tax_router, prefix="/v1/tax", tags=["tax"])
app.include_router(reporting_router, prefix="/v1/reports", tags=["reporting"])
app.include_router(files_router, prefix="/v1/files", tags=["files"])
app.include_router(billing_router, prefix="/v1/billing", tags=["billing"])
app.include_router(ai_router, prefix="/v1/ai", tags=["ai"])


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
