from fastapi import APIRouter
from sqlmodel import select

from app.dependencies import ActiveWorkspace, CurrentUser, DbSession
from app.modules.purchases.models import Bill, BillCreate, Vendor, VendorCreate
from app.modules.purchases.services import create_bill as create_bill_service
from app.modules.purchases.services import create_vendor as create_vendor_service

router = APIRouter()


@router.post("/vendors")
async def create_vendor(
    body: VendorCreate, workspace: ActiveWorkspace, user: CurrentUser, db: DbSession
):
    """Did not exist before — Bill.vendor_id had nothing to point at
    without this. Required before POST /bills can be used meaningfully."""
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
    """Now posts to the ledger (debit account_id, credit Accounts
    Payable) instead of just creating a row invisible to every report —
    see purchases/services.py."""
    bill = await create_bill_service(
        db, tenant_id=workspace, actor_user_id=user["sub"], body=body
    )
    return {"id": bill.id, "journal_entry_id": bill.journal_entry_id}


@router.get("/bills")
async def list_bills(workspace: ActiveWorkspace, db: DbSession):
    rows = await db.exec(select(Bill).where(Bill.tenant_id == workspace))
    return rows.all()