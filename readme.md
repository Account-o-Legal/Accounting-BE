# Account-o-Legal

Multi-client accounting platform for accountants and lawyers serving SMBs.

**Core idea:** import transactions, review AI-assisted categorization, approve, and generate books. The accountant manages many client workspaces from a single login.

---

## MVP Scope

### Included

* Multi-client workspaces
* JWT authentication
* RBAC
* Workspace switching
* Pakistan Chart of Accounts (pre-seeded)
* Double-entry accounting engine
* Journal entries
* Accounting periods
* Bank accounts
* CSV/OFX import
* Transaction review queue
* Rule-based transaction categorization
* Invoicing
* Bills
* Customers
* Vendors
* Tax tracking
* Audit logging
* Trial Balance
* Profit & Loss
* Balance Sheet
* Cash Flow
* Stripe billing
* OpenTelemetry observability

### Explicitly Excluded

* Auto-posting AI
* Multi-currency
* Anomaly detection
* Cash-flow coaching
* Automation engine
* Collaboration threads
* JazzCash
* EasyPaisa
* Multiple jurisdictions

---

## Product Principles

### 1. Multi-client first

This is not an SMB bookkeeping app.

The primary user is an accountant managing multiple clients.

Workspace switching is a first-class feature.

### 2. AI suggests, humans approve

The system never posts transactions automatically.

Flow:

Import CSV
→ Categorize
→ Review Queue
→ Approve
→ Journal Entry Posted

### 3. Rules before LLMs

MVP categorization is rule-based.

Unknown transactions enter the review queue.

LLM fallback remains disabled until sufficient production data exists.

### 4. Ledger correctness beats AI cleverness

If forced to choose:

Correct books > Smart suggestions

---

## Architecture

```text
Client
  ↓
FastAPI
  ↓
Modules
  ├── auth
  ├── accounting_core
  ├── banking
  ├── sales
  ├── purchases
  ├── tax
  ├── reporting
  ├── files
  ├── billing
  └── ai
  ↓
PostgreSQL
```

Async background jobs:

```text
arq
 ├── import_worker
 └── report_worker
```

---

## Project Structure

```text
app/
├── core/
├── db/
├── middleware/
├── observability/
├── workers/
│
└── modules/
    ├── auth/
    ├── accounting_core/
    ├── banking/
    ├── sales/
    ├── purchases/
    ├── tax/
    ├── reporting/
    ├── files/
    ├── billing/
    └── ai/

alembic/
tests/
```

---

## Tech Stack

| Area          | Technology    |
| ------------- | ------------- |
| API           | FastAPI       |
| ORM           | SQLModel      |
| Database      | PostgreSQL    |
| Migrations    | Alembic       |
| Queue         | ARQ           |
| Cache/Broker  | Redis         |
| Auth          | JWT           |
| IDs           | ULID          |
| Observability | OpenTelemetry |
| Runtime       | Python 3.13   |

---

## Local Development

### Create Environment

```bash
uv sync
```

### Run API

```bash
uv run uvicorn app.main:app --reload
```

### Run Migrations

```bash
uv run alembic upgrade head
```

### Run Worker

```bash
uv run arq app.workers.settings.WorkerSettings
```

---

## Current MVP Workflow

### 1. Register

```text
User
 ↓
Workspace Created
 ↓
Chart of Accounts Seeded
 ↓
Default Bank Account Created
```

### 2. Import Transactions

```text
CSV
 ↓
Import Worker
 ↓
Bank Transactions
```

### 3. Categorize

```text
Vendor Rule Match
 ↓
Suggested Account
```

Unknown transactions:

```text
Needs Review
```

### 4. Approve

```text
Bank Transaction
 ↓
Balanced Journal Entry
 ↓
Posted
```

---

## Database Rules

### Multi-tenancy

Every tenant-scoped table must contain:

```python
tenant_id: str
```

Queries must always filter by tenant.

### IDs

Use ULIDs.

Do not use:

* Auto increment IDs
* UUID4

### Accounting

Every posted journal entry must satisfy:

```text
Sum(Debits) == Sum(Credits)
```

No exceptions.

---

## Tests

Run critical money-path tests before every merge.

```bash
uv run python -m app.modules.accounting_core.test_services
```

Expected:

```text
ok
```

```bash
uv run python -m app.modules.banking.test_approve_transaction
```

Expected:

```text
ok
```

---

## MVP Definition of Done

An accountant can:

1. Create a workspace
2. Receive a pre-seeded Pakistan Chart of Accounts
3. Import a bank statement
4. Review categorized transactions
5. Approve transactions
6. Generate Trial Balance
7. Generate P&L
8. Generate Balance Sheet
9. Generate Cash Flow

Without creating manual journal entries.

---

## Status

### Working

* Authentication
* Workspaces
* CoA seeding
* Ledger engine
* Journal posting
* Transaction approval
* Rule-based categorization

### In Progress

* Import worker integration tests
* Reporting
* Tax workflows
* Billing

### Deferred

* LLM categorization
* Auto bank feeds
* Multi-currency
* Anomaly detection
* Cash-flow coaching
* Collaboration workflows

---

## License

Private proprietary software.
