# Software Requirements Specification — Account-o-Legal (MVP)

## 1. Purpose

Defines the functional and technical requirements for the MVP backend described in PRD.md: a multi-client accounting platform for accountants/lawyers, with narrow AI-assisted transaction categorization.

## 2. Tech Stack

- **Language/runtime:** Python 3.12–3.13 (3.14 has known SQLModel/Pydantic incompatibilities as of this writing — avoid until upstream fixes land)
- **Web framework:** FastAPI
- **ORM/schema:** SQLModel (wraps SQLAlchemy 2.0.49+), single class for ORM model + Pydantic schema to avoid duplication
- **DB:** PostgreSQL, async via `asyncpg`
- **Migrations:** Alembic, `SQLModel.metadata` as target
- **Queue/workers:** Redis-backed async jobs (`arq`) — 2 MVP queues: import, reports
- **Observability:** OpenTelemetry + structlog, single consolidated `observability/otel.py`
- **Auth:** JWT, OTP (email/phone), `passlib`/`bcrypt` for password hashing, `pyotp` for TOTP

## 3. Module Structure (trimmed to MVP scope)

```
app/modules/
├── auth/             # users, workspaces, workspace switcher, RBAC
├── accounting_core/  # Chart of Accounts, double-entry engine, periods, CoA seeding
├── sales/            # invoices, customers
├── purchases/        # bills, vendors
├── banking/           # bank accounts, transaction import, review queue, reconciliation
├── tax/               # FBR GST rates + tax transactions only (no audit code)
├── reporting/         # P&L, Balance Sheet, Trial Balance, Cash Flow, cross-client roll-up
├── files/             # receipt/document storage
├── billing/           # PKR plans, Stripe
└── ai/                # rules-first + LLM-fallback categorization (single explainability service)

app/core/              # config, security, exceptions, audit (cross-cutting, NOT under tax/)
app/db/                # session, mixins (ULID, tenant)
app/middleware/        # idempotency, tenant context (rate limiting deferred to V2)
app/observability/     # single otel.py (init + tracer + custom metrics)
app/workers/           # import_worker.py, report_worker.py
alembic/                # versions/, env.py referencing SQLModel.metadata
tests/
```

**Explicitly excluded from MVP module tree:** `automation/`, `collaboration/`, standalone `currency/` module (folded into `accounting_core` as an `fx_rate` field), multi-file `ai/` gateway, 5-way worker split, multi-file observability split. These are added only when their corresponding phase (V2/V3) begins.

**Structural correction applied:** audit logging lives in `core/audit.py`, not under `tax/` — it is a cross-cutting concern used by every module's mutations, not a tax-specific one.

## 4. Functional Requirements

### 4.1 Auth & Workspaces
- FR-1: Users register with email/password; a workspace is created and the user is added as `owner`.
- FR-2: On workspace creation, the system seeds the workspace's Chart of Accounts from its jurisdiction pack (e.g. `pk.json`) so the workspace is never empty.
- FR-3: On workspace creation, if a default "Bank Account" ledger account exists (code `1020` in the PK pack), a matching `BankAccount` row is created automatically.
- FR-4: `GET /workspaces` returns every workspace the authenticated user belongs to, with their role — powers the multi-client workspace switcher.
- FR-5: Roles are enforced per-workspace (RBAC), not globally on the JWT alone.

### 4.2 Accounting Core
- FR-6: Every journal entry must balance (sum of debits == sum of credits) before posting; unbalanced entries are rejected.
- FR-7: Accounts support a self-referencing parent/child hierarchy.
- FR-8: Periods can be marked closed to prevent further postings (enforcement may be deferred to V2 but the field exists in MVP schema).

### 4.3 AI Categorization
- FR-9: Bank transactions are categorized by rule-based vendor/memo matching first.
- FR-10: Transactions the rules can't confidently match fall back to an LLM suggestion.
- FR-11: No categorization is auto-posted. Every suggestion requires explicit user approval via the review queue before a journal entry is created.
- FR-12: On approval, the system builds a balanced two-line journal entry: one leg against the bank's linked ledger account, one leg against the categorized (suggested) account, with debit/credit direction determined by inflow vs outflow.

### 4.4 Banking
- FR-13: Bank transactions can be imported via CSV/OFX, processed asynchronously.
- FR-14: Each `BankAccount` must reference a `ledger_account_id` so approved transactions have a real ledger account to post against.

### 4.5 Reporting
- FR-15: P&L, Balance Sheet, Trial Balance, and Cash Flow reports are available per client workspace.
- FR-16: A roll-up view aggregates reporting data across all workspaces an accountant has access to.

### 4.6 Tax
- FR-17: FBR GST rates and tax transactions are tracked per workspace.

## 5. Non-Functional Requirements

- NFR-1: Workspace switching must complete in under 1 second (core UX differentiator).
- NFR-2: All money-path logic (balance checks, transaction approval/posting) must ship with a runnable test, not just type-checked code.
- NFR-3: Multi-tenancy is enforced at the data layer — every tenant-scoped table carries a `tenant_id` and queries must filter by it.
- NFR-4: Audit logging captures actor, entity type/id, action, and a diff for every mutating operation across modules.
- NFR-5: AI inference cost must stay low — rules must handle the majority of transactions; the LLM fallback is reserved for ambiguous cases only.

## 6. Data Model Notes

- IDs are ULIDs (sortable, string primary keys), not UUIDs or auto-increment ints.
- 17 MVP tables, created in FK-safe order: `users`, `workspaces`, `workspace_members`, `accounts`, `journal_entries`, `journal_lines`, `accounting_periods`, `audit_log_entries`, `customers`, `invoices`, `tax_rates`, `fbr_filings`, `invoice_lines`, `vendors`, `bills`, `bank_accounts`, `bank_transactions`.

## 7. Known Gaps / Unverified Items (as of MVP scaffold)

- Initial Alembic migration (`0001_initial`) was hand-written, not autogenerated against a live DB — must be verified with `alembic upgrade head` against a real Postgres instance.
- CSV/OFX parsing (`import_worker.py`) is stubbed, not implemented.
- FBR API integration, Stripe checkout, PDF rendering, virus scanning are stubbed.
- Debit/credit sign convention for inflow/outflow must be confirmed by an accountant before processing real transactions.
- Rate limiting middleware deferred to V2.

## 8. Environment Requirements

- Python 3.12 or 3.13 (avoid 3.14 until SQLAlchemy/SQLModel/Pydantic compatibility is confirmed stable).
- `sqlmodel==0.0.22`, `sqlalchemy[asyncio]==2.0.49` or later.
- PostgreSQL (async via `asyncpg`).
- Redis for async job queues.
