from fastapi import APIRouter

from app.core.audit import record_audit_event
from app.dependencies import ActiveWorkspace, CurrentUser, DbSession
from app.modules.purchases.models import Bill, BillCreate

router = APIRouter()


@router.post("/bills")
async def create_bill(
    body: BillCreate, workspace: ActiveWorkspace, user: CurrentUser, db: DbSession
):
    bill = Bill(tenant_id=workspace, **body.model_dump())
    db.add(bill)
    await db.flush()
    await record_audit_event(
        db,
        tenant_id=workspace,
        actor_user_id=user["sub"],
        entity_type="bill",
        entity_id=bill.id,
        action="create",
        diff_json=f'{{"vendor_id": "{bill.vendor_id}", "amount": {bill.amount}}}',
    )
    await db.commit()
    return {"id": bill.id}