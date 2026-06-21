"""Standard reports, per-workspace — plus one MVP-specific view:
the accountant's cross-client dashboard. That roll-up is part of the
"multi-client" pitch (see auth module) just as much as the switcher is;
without it, having many workspaces is just a longer dropdown, not a
genuine multi-client tool.
"""

from datetime import date

from fastapi import APIRouter
from sqlmodel import func, select

from app.dependencies import ActiveWorkspace, CurrentUser, DbSession
from app.modules.auth.models import Workspace, WorkspaceMember
from app.modules.banking.models import BankTransaction
from app.modules.reporting.services import (
    generate_balance_sheet,
    generate_profit_and_loss,
    generate_trial_balance,
)

router = APIRouter()


@router.get("/trial-balance")
async def trial_balance(workspace: ActiveWorkspace, db: DbSession):
    """The proof report: if the ledger is correct, total_debit ==
    total_credit always, for any tenant, regardless of transaction
    volume. See reporting/services.py's test_trial_balance.py for the
    invariant this enforces."""
    return await generate_trial_balance(db, tenant_id=workspace)


@router.get("/profit-and-loss")
async def profit_and_loss(
    workspace: ActiveWorkspace,
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
):
    return await generate_profit_and_loss(
        db, tenant_id=workspace, start_date=start_date, end_date=end_date
    )


@router.get("/balance-sheet")
async def balance_sheet(workspace: ActiveWorkspace, db: DbSession, as_of: date | None = None):
    return await generate_balance_sheet(db, tenant_id=workspace, as_of=as_of)


@router.get("/across-clients")
async def cross_client_summary(user: CurrentUser, db: DbSession):
    """One row per workspace this accountant has access to, surfacing the
    two things that actually matter for triage across many clients:
    - pending_review_count: transactions sitting in the review queue
      (needs_review or ai_suggested) — this is the "what needs my
      attention today" number.
    - is_balanced: whether that workspace's trial balance currently ties
      out — the trust signal. A workspace coming back unbalanced here is
      worth investigating immediately (it shouldn't be possible given
      post_journal_entry's balance check, but this is the cross-client
      view's job to notice if it ever somehow happened).

    This is the view that's impossible in a single-tenant tool and is
    exactly why a multi-client accountant would switch to this product —
    one glance tells them which of their clients' books need work, without
    opening each workspace one at a time.

    ponytail: this fans out one trial-balance query + one count query per
    workspace the user belongs to (2N queries for N workspaces). Fine for
    the realistic MVP scale (an accountant managing tens, not thousands,
    of clients); revisit with a single aggregated query or a materialized
    summary table only if that assumption breaks in practice.
    """
    memberships = (
        await db.exec(
            select(Workspace.id, Workspace.name, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user["sub"])
        )
    ).all()

    results = []
    for workspace_id, workspace_name, role in memberships:
        pending_count = (
            await db.exec(
                select(func.count(BankTransaction.id)).where(
                    BankTransaction.tenant_id == workspace_id,
                    BankTransaction.category_status.in_(["needs_review", "ai_suggested"]),
                )
            )
        ).one()

        trial_balance_data = await generate_trial_balance(db, tenant_id=workspace_id)

        results.append(
            {
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "role": role,
                "pending_review_count": pending_count,
                "is_balanced": trial_balance_data["is_balanced"],
            }
        )

    # Workspaces with pending work surface first — that's the triage order
    # an accountant actually wants when scanning across many clients.
    results.sort(key=lambda r: r["pending_review_count"], reverse=True)

    return {"workspaces": results}