from app.modules.auth.models import User, Workspace, WorkspaceMember


async def make_workspace(db_session, name="Test Client Co"):
    ws = Workspace(name=name, jurisdiction_code="pk")
    db_session.add(ws)
    await db_session.flush()
    return ws


async def make_user_with_workspace(db_session, email="accountant@example.com"):
    """The realistic MVP fixture: one accountant, one client workspace,
    matching the multi-tenant model the whole product is built on."""
    user = User(email=email, password_hash="x")
    ws = await make_workspace(db_session)
    db_session.add(user)
    await db_session.flush()
    db_session.add(WorkspaceMember(user_id=user.id, workspace_id=ws.id, role="owner"))
    await db_session.commit()
    return user, ws
