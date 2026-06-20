"""Auth module owns: users, workspaces (= tenants = "clients" in the
accountant's world), and membership linking the two.

This is the structural core of the MVP pitch: one user (the accountant)
can belong to many workspaces (their clients' books). WorkspaceMember is
the join table the workspace switcher reads from.
"""

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.core.enums import Role
from app.db.mixins import TimestampMixin, ULIDMixin


class User(ULIDMixin, TimestampMixin, SQLModel, table=True):
    __tablename__ = "users"

    email: str = Field(unique=True, index=True, max_length=255)
    phone: str | None = Field(default=None, unique=True, max_length=32)
    password_hash: str
    totp_secret: str | None = None
    is_active: bool = Field(default=True)


class Workspace(ULIDMixin, TimestampMixin, SQLModel, table=True):
    """A workspace == one client's set of books. jurisdiction_code drives
    every tax/CoA/currency default per the platform's jurisdiction-first
    principle — set once at creation, never hardcoded downstream."""

    __tablename__ = "workspaces"

    name: str
    jurisdiction_code: str = Field(default="pk", max_length=8)


class WorkspaceMember(ULIDMixin, SQLModel, table=True):
    """Join table: which users can access which workspaces, with what role.
    This is what the workspace switcher queries to populate the dropdown."""

    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id"),)

    user_id: str = Field(foreign_key="users.id", index=True)
    workspace_id: str = Field(foreign_key="workspaces.id", index=True)
    role: Role = Field(default=Role.VIEWER)


# --- Request/response shapes ---

class RegisterRequest(SQLModel):
    email: str
    password: str
    workspace_name: str


class LoginRequest(SQLModel):
    email: str
    password: str


class WorkspaceSummary(SQLModel):
    id: str
    name: str
    role: str
