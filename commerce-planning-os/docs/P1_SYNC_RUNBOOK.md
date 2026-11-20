# P1 Read-only Shopify sync and private API: operator runbook

**Status**: verified end-to-end with MOCK Shopify HTTPS payload and REAL ephemeral
PostgreSQL 16 in GitHub Actions. Not connected to persistent staging, not approved
for real merchant data, and NOT production deployed.

## Source code
- `shopify_transport.py`: strict canonical myshopify.com domain, TLS, POST
  carrying *only* allowlisted GraphQL read query, timeout, HTTP error handling,
  bounded 429/5xx retries and secret stored in server-side environment only.
- `shopify_readonly.py`: source validation, all-or-nothing paginated pull,
  stable content hash ignoring acquisition timestamp, supplier count check.
  Product variants with >100 records are deliberately blocked (need nested
  pagination instead of truncating source data).
- `sync_worker.py`: one-shot read-only full-sync orchestration, optional count
  cross-check, atomic PostgreSQL ingestion, not publicly served.
- `postgres_store.py`: transactional store-scoped products, variants, source
  snapshots, sync run. Idempotent incoming state, out-of-order updates ignored.
- `internal_api.py`: backend-only WSGI read endpoint requiring a strong
  internal token and a store allowlist; bound to loopback in `main()`.
  This is **not** an end-user OIDC/RBAC replacement.

## Requirements before an isolated staging deployment with real data
1. Provision a persistent PostgreSQL 16 database under dedicated private
   network access; create database roles and RLS policies (not yet supplied).
2. Apply `database/migrations/001_init.sql` to staging database, review
   migration transaction and verify the successful schema version.
3. Obtain a separate read-only Shopify Admin access token via the store's
   approved app installation, with only the required read scopes. Never
   copy credentials into GitHub issues, app frontend, commits or chats.
4. Configure server-side secret manager to inject:
   `COMMERCE_STORE_ID`, `COMMERCE_SHOPIFY_DOMAIN` (myshopify.com canonical),
   `COMMERCE_SHOPIFY_READ_TOKEN`, `COMMERCE_PG_DSN`.
5. Review and register the store with `put_store()` via a migration/admin-only
   process, not an unauthenticated endpoint.
6. Execute `python -m commerce_os.sync_worker` from the backend host only.
   Enforce source-count reconciliation, paging and observability; audit run
   logs, result counts, timestamps and variant completeness.
7. Protect any API behind TLS gateway + OIDC/RBAC BFF. The service-to-service
   token alone does NOT authorize an end user. Use `COMMERCE_INTERNAL_API_TOKEN`
   and `COMMERCE_ALLOWED_STORES` only on backend.
8. Perform permission denial, cross-brand isolation, backups and restore,
   full inventory location reconciliation, cost availability review, and
   regression tests before enabling full catalog sync.

## Reproducible integration test
GitHub Action `commerce-os-ci.yml` boots PostgreSQL 16 and runs:
`cd commerce-planning-os && python -m unittest discover -s tests -v`.
Full-pipeline integration test uses a stub HTTPS response and a real SQL
transaction; the mock fixture is NOT a claim of real Shopify data replication.

## Safe rollback
- GitHub: PR #15 stays in draft; no merge. Feature branch can be reverted
  without touching repository root `index.html`.
- AppDeploy: separate fixture-only UI preview has version rollback verification.
- Database: **not yet qualified for live staging rollback**. Do not use
  automatic schema rollback without restoring a tested backup.

## Explicit release hold
No persistent database, no production Shopify Worker deployment, no nested
variant pagination beyond 100, no incremental checkpointing, no OIDC/RBAC,
no completed independent security audit, no integrated real-data Dashboard.
Therefore P1 full acceptance remains BLOCKED.
