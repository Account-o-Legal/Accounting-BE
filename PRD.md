# Product Requirements Document — Account-o-Legal

## 1. Product Vision

Not "QuickBooks clone with AI sprinkled in."

**Is:** The multi-client books platform for accountants and lawyers serving SMBs — switch clients in one click, AI proposes every entry, you just approve.

## 2. Target User

- **Primary buyer:** Accountants and lawyers managing books for multiple SMB clients (not the SMB owner directly).
- **Why they switch from Excel / QuickBooks / a local bookkeeper:** they currently juggle many clients with no fast way to switch context, and they re-key transactions by hand.

## 3. Core Differentiators (the hills we die on)

1. **Multi-client workspace switching** — core to the pitch, not a V2/enterprise feature. An accountant logs in once and switches between client books in under a second.
2. **AI does the bookkeeping, narrow and cheap** — rule-based categorization (vendor/memo matching) covers ~80% of transactions; an LLM fallback handles the ambiguous ~20%. The system **suggests, never auto-posts** — a human always approves before anything hits the ledger. This keeps trust high and AI spend low.
3. **UX that doesn't feel like accounting** — a one-tap Tinder-style review queue instead of manual data entry.

## 4. Explicit Scope Cuts (and why)

- **JazzCash/EasyPaisa payment collection** — cut from MVP. The buyer is an accountant managing books, not collecting payments from end customers. Pushed to V2.
- **Auto-posting (unsupervised AI)** — deliberately not MVP. Trust has to be earned first; this is a V2+ feature.
- **Multi-currency, anomaly detection, cash-flow coaching, automation/workflow engine, collaboration threads, second jurisdiction** — all explicitly out of MVP (see Section 6).

## 5. Phase 1 — MVP (Months 1–4): "Multi-client books, AI-assisted"

| Area | Deliverables | Why it's here |
|---|---|---|
| **Auth & Workspaces** | Email/phone OTP, JWT, RBAC, multi-client workspace switcher, per-client invite (accountant invites SMB owner as viewer, or vice versa) | This *is* the pitch |
| **Accounting Core** | CoA (PK default template), double-entry engine, journal entries, periods | Non-negotiable foundation |
| **AI Categorization (narrow)** | Rule-based categorization (vendor/memo matching) for ~80% of transactions; LLM fallback for ambiguous ones; suggest-only journal entries with one-tap approve/reject UI | The "AI does bookkeeping" hill, cheap version |
| **Sales & Purchases** | Invoicing, bills, customer/vendor records, receipt upload | Needed to generate transactions to categorize |
| **Banking** | CSV/OFX import (async), reconciliation feeding the categorization engine | Source of truth for AI suggestions |
| **Tax** | FBR GST setup, tax transactions, audit log (lives in core, not tax module) | Required for PK launch |
| **Reporting** | P&L, Balance Sheet, Trial Balance, Cash Flow | Table stakes — per-client *and* a roll-up view across an accountant's clients |
| **UX differentiator** | One-tap transaction review queue, fast client-switch (<1s), minimal-click invoice creation | The "doesn't feel like accounting" hill |
| **Billing** | PKR plans, Stripe only (skip JazzCash/EasyPaisa) | Cut to fund the above |
| **Observability** | Full OTel/Prometheus/Loki/Grafana | Cheap to build in from day 1, expensive to retrofit |

## 6. Phase 2 — V2 (Months 5–9): "Trust the AI more, scale the firm"

| Area | Deliverables |
|---|---|
| Banking | Auto bank feeds, smart rule refinement from approval history |
| AI | Anomaly detection (flag unusual transactions across all clients in one inbox) |
| Automation | Recurring invoices/bills, payment gateway webhooks, JazzCash/EasyPaisa |
| Collaboration | Client handoff, comment threads, approval workflows |
| Reporting | Budget vs actual, cross-client benchmarking |
| Industry packs | CoA templates for common SMB types accountants serve |

## 7. Phase 3 — V3 (Months 10–16): "Coach, not just bookkeeper"

| Area | Deliverables |
|---|---|
| AI | Cash-flow coaching, 30/60/90-day forecast, pricing/proposal assistant |
| Automation | Marketplace, partner connectors |
| Legal | Dispute bundle export (for the "lawyers" segment specifically) |
| Enterprise | Multi-entity consolidation, custom workflows |
| Global | Second jurisdiction pack, multi-region residency |

## 8. Success Criteria for MVP

- An accountant can sign up, get a workspace pre-seeded with a PK Chart of Accounts, switch between client workspaces in under a second, import a bank CSV, see AI-suggested categorizations, approve them with one tap, and pull P&L/Balance Sheet/Trial Balance/Cash Flow reports — all without manual journal entry.

## 9. Open Risks / Decisions Pending

- Sign convention for inflow/outflow journal lines must be validated by an accountant before touching real money.
- FBR API integration scope and rate limits not yet finalized.
- Exact LLM fallback cost ceiling per transaction not yet set.
