from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from app.dependencies import ActiveWorkspace, CurrentUser, DbSession
from app.modules.purchases.models import Bill, BillCreate, Vendor, VendorCreate
from app.modules.purchases.services import (
    create_bill as create_bill_service,
    create_vendor as create_vendor_service,
    pay_bill as pay_bill_service,
)

router = APIRouter()


class PayBillRequest(BaseModel):
    bank_account_id: str


@router.post("/vendors")
async def create_vendor(
    body: VendorCreate, workspace: ActiveWorkspace, user: CurrentUser, db: DbSession
):
    vendor = await create_vendor_service(
        db, tenant_id=workspace, actor_user_id=user["sub"], body=body
    )
    return {"id": vendor.id, "name": vendor.name}


@router.get("/vendors")
async def list_vendors(workspace: ActiveWorkspace, db: DbSession):
    rows = await db.exec(select(Vendor).where(Vendor.tenant_id == workspace))
    return rows.all()


@router.post("/bills")
async def create_bill(
    body: BillCreate, workspace: ActiveWorkspace, user: CurrentUser, db: DbSession
):
    """Posts entry 1 (debit Expense, credit AP) — see services.py."""
    bill = await create_bill_service(
        db, tenant_id=workspace, actor_user_id=user["sub"], body=body
    )
    return {"id": bill.id, "journal_entry_id": bill.journal_entry_id}


@router.post("/bills/{bill_id}/pay")
async def pay_bill(
    bill_id: str, body: PayBillRequest, workspace: ActiveWorkspace, user: CurrentUser, db: DbSession
):
    """Posts entry 2 (debit AP, credit Bank) — completes the two-entry
    bill lifecycle so AP nets to zero and the bank balance reflects the
    cash outflow. Makes is_paid mean something in the books, not just
    cosmetically."""
    bill = await pay_bill_service(
        db,
        tenant_id=workspace,
        actor_user_id=user["sub"],
        bill_id=bill_id,
        bank_account_id=body.bank_account_id,
    )
    return {"id": bill.id, "is_paid": bill.is_paid}


@router.get("/bills")
async def list_bills(workspace: ActiveWorkspace, db: DbSession):
    rows = await db.exec(select(Bill).where(Bill.tenant_id == workspace))
    return rows.all()