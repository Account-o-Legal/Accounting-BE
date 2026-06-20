"""Subscription billing. Stripe only for MVP — JazzCash/EasyPaisa moved to
V2 per the phase rebuild (accountant managing books != accountant
collecting customer payments; the latter isn't the show-stopper)."""

from fastapi import APIRouter

from app.dependencies import ActiveWorkspace

router = APIRouter()


@router.get("/plans")
async def list_plans():
    # ponytail: plans are a static list, not a pricing-engine table, until
    # there's a second pricing tier that actually needs runtime config.
    return [
        {"id": "starter", "name": "Starter", "price_pkr": 2000, "max_workspaces": 3},
        {"id": "firm", "name": "Firm", "price_pkr": 8000, "max_workspaces": 25},
    ]


@router.post("/checkout")
async def create_checkout_session(plan_id: str, workspace: ActiveWorkspace):
    # ponytail: Stripe Checkout session creation — straightforward SDK
    # call, stubbed until Stripe account + webhook endpoint exist.
    raise NotImplementedError
