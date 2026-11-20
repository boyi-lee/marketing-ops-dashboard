# P1 Data Foundation: implementation and limitations

## Scope built in this branch
- PostgreSQL 001_init.sql migration defines store-scoped identifiers, source snapshots,
  product and variant masters, inbound schedules, external cost records, plan drafts,
  audit events, checkpoint and synchronization runs.
- `shopify_readonly.py` implements a **query-only, dependency-injected**
  product pagination and validation adapter with finite retry, duplicate and
  repeated cursor checks, nested variant pagination truncation fail-closed.
- Cost is deliberately NOT inferred from product selling price. Distinct
  finance import / cost record flow must be built and approved.
- Source and normalized record count comparison flags mismatches.

## Architecture boundary
Shopify MCP is conversational, not a durable database. The production sync worker
will use a separately provisioned Shopify Admin GraphQL read-only credential.
It must implement network rate limits/backoff, operational retries, run state,
initial and incremental backfills, and secure token refresh. Those are **not
yet deployed**. This prototype does not persist real Shopify payloads.

## Gate status
- Python adapter, unit tests: GitHub CI.
- SQL migration file: generated but not applied to a real PostgreSQL instance.
- Formal schema migrations, grants/RLS and backup: blocked until protected staging
  database is provisioned.
- No secrets, customer PII or real Shopify item records in git.

## Next required module work
M01: production-grade worker transport, nested variant pagination, transactional
batch writes, cursor and retry-after backoff.
M02: inbound/cost CSV contract + actual import and review.
M03/M04: snapshots, data quality, SQL constraints, reconciliation with official
source (multiple store currencies and cost completeness).
M13/M14: OIDC/roles, per-store isolation, secret manager and restore rehearsal.
