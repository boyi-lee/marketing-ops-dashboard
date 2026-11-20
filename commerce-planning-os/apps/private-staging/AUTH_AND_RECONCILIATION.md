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
