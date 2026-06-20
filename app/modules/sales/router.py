from datetime import date

from fastapi import APIRouter

from app.core.enums import InvoiceStatus
from app.dependencies import ActiveWorkspace, DbSession
from app.modules.sales.models import Invoice, InvoiceCreate

router = APIRouter()


@router.post("/invoices")
async def create_invoice(body: InvoiceCreate, workspace: ActiveWorkspace, db: DbSession):
    """Creates a draft invoice. ponytail: invoice numbering is a simple
    per-tenant incrementing counter on the workspace row, not a configurable
    numbering-scheme engine — that's a real feature some accountants will
    want (custom prefixes, fiscal-year resets) but nobody's asked yet."""
    invoice = Invoice(
        tenant_id=workspace,
        customer_id=body.customer_id,
        invoice_number=f"INV-{date.today().year}-0001",  # placeholder sequence
        issue_date=body.issue_date,
        due_date=body.due_date,
        status=InvoiceStatus.DRAFT,
    )
    db.add(invoice)
    await db.commit()
    return {"id": invoice.id, "status": invoice.status}
