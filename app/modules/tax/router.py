from fastapi import APIRouter
from sqlmodel import select

from app.dependencies import ActiveWorkspace, DbSession
from app.modules.tax.models import TaxRate

router = APIRouter()


@router.get("/rates")
async def list_tax_rates(workspace: ActiveWorkspace, db: DbSession):
    rows = await db.exec(select(TaxRate).where(TaxRate.tenant_id == workspace))
    return rows.all()
