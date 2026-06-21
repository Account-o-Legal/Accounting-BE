"""Auth + workspace switcher endpoints.

GET /workspaces is the endpoint the frontend's workspace switcher dropdown
calls — returns every client the logged-in accountant has access to.
"""

from fastapi import APIRouter
from sqlmodel import select

from app.core.audit import record_audit_event
from app.core.security import create_jwt, hash_password, verify_password
from app.dependencies import CurrentUser, DbSession
from app.modules.accounting_core.seed import find_account_by_code, seed_chart_of_accounts
from app.modules.auth.models import (
    LoginRequest,
    RegisterRequest,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceSummary,
)
from app.modules.banking.models import BankAccount

router = APIRouter()


@router.post("/register")
async def register(body: RegisterRequest, db: DbSession):
    user = User(email=body.email, password_hash=hash_password(body.password))
    workspace = Workspace(name=body.workspace_name)
    db.add(user)
    db.add(workspace)
    await db.flush()
    db.add(WorkspaceMember(user_id=user.id, workspace_id=workspace.id, role="owner"))

    # Seed the CoA immediately so this workspace isn't empty — without
    # this, AI categorization and approve_transaction have no accounts
    # to work with on day one.
    accounts = await seed_chart_of_accounts(
        db, tenant_id=workspace.id, jurisdiction_code=workspace.jurisdiction_code
    )
    bank_ledger_account = find_account_by_code(accounts, "1020")  # "Bank Account" in pk.json
    if bank_ledger_account:
        db.add(
            BankAccount(
                tenant_id=workspace.id,
                name="Primary Bank Account",
                ledger_account_id=bank_ledger_account.id,
            )
        )
    # ponytail: if the jurisdiction pack doesn't define code "1020" this
    # silently skips creating a default BankAccount rather than failing
    # registration — a missing default account shouldn't block onboarding,
    # the accountant can add a bank account manually in that edge case.

    # Actor is the new user themselves — there's no other logged-in
    # identity to attribute workspace creation to at registration time.
    await record_audit_event(
        db,
        tenant_id=workspace.id,
        actor_user_id=user.id,
        entity_type="workspace",
        entity_id=workspace.id,
        action="create",
        diff_json=f'{{"name": "{workspace.name}", "jurisdiction_code": "{workspace.jurisdiction_code}"}}',
    )

    await db.commit()
    token = create_jwt(user.id, [workspace.id], role="owner")
    return {"access_token": token}


@router.post("/login")
async def login(body: LoginRequest, db: DbSession):
    user = (await db.exec(select(User).where(User.email == body.email))).first()
    if not user or not verify_password(body.password, user.password_hash):
        from app.core.exceptions import UnauthorizedError
        raise UnauthorizedError("Invalid credentials")

    memberships = (
        await db.exec(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
    ).all()
    workspace_ids = [m.workspace_id for m in memberships]
    # ponytail: role on the JWT is the role in the FIRST workspace only;
    # per-workspace role is re-checked via get_active_workspace on each
    # request anyway, so this top-level field is just a convenience default.
    token = create_jwt(user.id, workspace_ids, role=memberships[0].role if memberships else "viewer")
    return {"access_token": token}


@router.get("/workspaces", response_model=list[WorkspaceSummary])
async def list_my_workspaces(user: CurrentUser, db: DbSession):
    """Powers the workspace switcher: every client this user can access."""
    rows = (
        await db.exec(
            select(Workspace.id, Workspace.name, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user["sub"])
        )
    ).all()
    return [WorkspaceSummary(id=r.id, name=r.name, role=r.role) for r in rows]