from fastapi import APIRouter
from sqlmodel import select

from app.dependencies import ActiveWorkspace, CurrentUser, DbSession
from app.modules.sales.models import Invoice, InvoiceCreate
from app.modules.sales.services import create_invoice as create_invoice_service

router = APIRouter()


@router.post("/invoices")
async def create_invoice(
    body: InvoiceCreate, workspace: ActiveWorkspace, user: CurrentUser, db: DbSession
):
    """Creates an invoice with its lines, a real sequential invoice
    number, and posts AR/Revenue/GST to the ledger immediately — see
    sales/services.py for why all three have to happen together."""
    invoice = await create_invoice_service(
        db, tenant_id=workspace, actor_user_id=user["sub"], body=body
    )
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "journal_entry_id": invoice.journal_entry_id,
    }


@router.get("/invoices")
async def list_invoices(workspace: ActiveWorkspace, db: DbSession):
    rows = await db.exec(select(Invoice).where(Invoice.tenant_id == workspace))
    return rows.all()


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, workspace: ActiveWorkspace, db: DbSession):
    from app.core.exceptions import NotFoundError
    from app.modules.sales.models import InvoiceLine

    invoice = (
        await db.exec(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == workspace)
        )
    ).first()
    if not invoice:
        raise NotFoundError("Invoice not found")

    lines = (
        await db.exec(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))
    ).all()
    return {"invoice": invoice, "lines": lines}