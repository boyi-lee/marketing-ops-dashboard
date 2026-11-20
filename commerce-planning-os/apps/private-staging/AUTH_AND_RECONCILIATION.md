# P1 AppDeploy Private Staging - Shopify 2026 Credential Flow

Protected app: https://commerce-planning-os-private-staging-pi20d7.v2.appdeploy.ai/
AppDeploy app id: commerce-planning-os-private-staging-pi20d7

Implementation:
- AppDeploy auth JWT required. Merchant data API restricted to verified `COMMERCE_OWNER_EMAIL`.
- Shopify store fixed to verified DESCENTE TW canonical domain `descente-tw.myshopify.com`.
- Shopify Admin GraphQL is **read-only**. User grants precisely `read_products` and `read_inventory`.
- New Dev Dashboard app uses client credentials grant. The backend exchanges encrypted
  `COMMERCE_SHOPIFY_CLIENT_ID` and `COMMERCE_SHOPIFY_CLIENT_SECRET` for an expiring access token.
- Tokens are cached in backend memory until 90 seconds before expiry; never stored in database,
  logs, browser code or the public GitHub repository.
- Using old permanent `COMMERCE_SHOPIFY_READ_TOKEN` is DEPRECATED for this deployment and not used.
- Shopify source count is queried with `productsCount(limit:null)`. Complete cursor traversal
  and count match is only a **preliminary count check**, not final source-to-data reconciliation.
- AppDeploy persistent database is **NOT** PostgreSQL. Python reference worker and PostgreSQL
  remain CI-tested separately. Do not claim this adapter deploys PostgreSQL.
- There is no autonomous background cron in the current staging adapter; sync is owner-triggered
  one bounded page at a time.

Required user-side secure configuration:
1. Enter exact sign-in email in COMMERCE_OWNER_EMAIL.
2. Enter `descente-tw.myshopify.com` in COMMERCE_SHOPIFY_DOMAIN.
3. Create/install an internal Shopify Dev Dashboard app in the store's organization,
   grant read_products and read_inventory only.
4. Enter Client ID and Client Secret via AppDeploy encrypted secret-entry widget.
5. Bind only submitted secrets to this app. Test owner authorization, connection, full
   catalog pagination, variant completeness, source count and snapshot lineage.

Do not put credentials in GitHub, chat or source files. External reference:
https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant

## Background sync and rollback evidence

- Deployment v5 had a scheduled `commerce-sync` cron every five minutes
  (`Asia/Taipei`), one bounded page of 30 products per invocation.
- The scheduler remains safely idle until owner/domain/client ID/client secret
  are securely bound. It must not handle real data without the approved app.
- Unsuppressed synchronization failures use a sanitized error identifier,
  retaining the last successful checkpoint and not disclosing secrets.
- The app-native persistent DB is **not PostgreSQL**; separate PG migration
  and authenticated network integration are still future gates.
- Rollback drill was performed: deployed version `1795158947574` (v5)
  reverted to `1795158652465` (v4) and was restored to v5; both became ready.
  **Caveat:** cron still appeared enabled when v4 was restored. Treat cron
  configuration as separately managed and verify/disable when rolling back.
- Current checked backend revision is later than the rollback-drill version;
  it marks scheduled synchronization errors rather than silently succeeding.
- Real full-catalog sync and data reconciliation remain BLOCKED until secret
  intake and formal source validation; never mark the 6,156 live source
  products as ingested solely because this code is deployed.
