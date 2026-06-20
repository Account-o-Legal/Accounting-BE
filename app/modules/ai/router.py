"""ponytail: MVP AI surface area is exactly two things — categorization
(services.py) and explaining a suggestion (this endpoint). Anomaly
detection and cash-flow coaching are V2/V3; no router stubs for them here
since an empty endpoint that 404s isn't more honest than no endpoint."""

from fastapi import APIRouter

from app.dependencies import ActiveWorkspace

router = APIRouter()


@router.get("/transactions/{txn_id}/explain")
async def explain_suggestion(txn_id: str, workspace: ActiveWorkspace):
    """Powers the 'why did you suggest this?' tap in the review queue —
    trust-building UI for a buyer (accountant) who won't approve a
    categorization they don't understand."""
    # ponytail: stub — wire to the matched rule or the LLM's own reasoning
    # (ask it to include a one-line 'why' in the same JSON response) once
    # the review queue UI exists to display it.
    return {"txn_id": txn_id, "explanation": "Matched vendor rule: 'K-Electric' -> Utilities"}
