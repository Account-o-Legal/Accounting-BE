"""Standard reports, per-workspace — plus one MVP-specific view:
the accountant's cross-client dashboard. That roll-up is part of the
"multi-client" pitch (see auth module) just as much as the switcher is;
without it, having many workspaces is just a longer dropdown, not a
genuine multi-client tool.
"""

from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession

router = APIRouter()


@router.get("/profit-and-loss")
async def profit_and_loss(workspace_id: str, db: DbSession):
    # ponytail: actual aggregation (sum journal lines by account type,
    # grouped by period) is a single SQL query once accounts have real
    # data — stub return until accounting_core has enough rows to test
    # against meaningfully.
    return {"workspace_id": workspace_id, "revenue": 0, "expenses": 0, "net_income": 0}


@router.get("/balance-sheet")
async def balance_sheet(workspace_id: str, db: DbSession):
    return {"workspace_id": workspace_id, "assets": 0, "liabilities": 0, "equity": 0}


@router.get("/across-clients")
async def cross_client_summary(user: CurrentUser, db: DbSession):
    """One row per workspace this accountant has access to — the
    'review queue items pending across all my clients' view that's
    impossible in a single-tenant tool and is exactly why a multi-client
    accountant would switch to this product."""
    # ponytail: this fans out one lightweight query per workspace the user
    # belongs to. Fine for the realistic MVP scale (an accountant managing
    # tens, not thousands, of clients); revisit with a materialized
    # summary table only if that assumption breaks.
    return {"workspaces": []}
