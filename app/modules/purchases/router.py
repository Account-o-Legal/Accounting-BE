from fastapi import APIRouter

from app.dependencies import ActiveWorkspace, DbSession
from app.modules.purchases.models import Bill, BillCreate

router = APIRouter()


@router.post("/bills")
async def create_bill(body: BillCreate, workspace: ActiveWorkspace, db: DbSession):
    bill = Bill(tenant_id=workspace, **body.model_dump())
    db.add(bill)
    await db.commit()
    return {"id": bill.id}
