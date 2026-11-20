# Private Staging adapter (AppDeploy)

Staging app ID: `commerce-planning-os-private-staging-pi20d7`.
URL: https://commerce-planning-os-private-staging-pi20d7.v2.appdeploy.ai/

This directory mirrors the deployed AppDeploy source snapshot, for code review and rollback.
It is a **TypeScript AppDeploy adapter** to the Commerce OS backend, NOT the Python/PostgreSQL deployment.
The database uses AppDeploy persistent key-value storage; no PostgreSQL instance is provisioned here.

Security gate:
- Requires AppDeploy login and an encrypted `COMMERCE_OWNER_EMAIL` allowlist.
- `COMMERCE_SHOPIFY_DOMAIN` must be canonical .myshopify.com domain.
- `COMMERCE_SHOPIFY_READ_TOKEN` remains server-side only, entered using AppDeploy secure secret-entry form.
- No API can read catalog data without approved authenticated owner.
- Sync is read-only Shopify GraphQL. Each click persists one page, with source cursor.
- No real data has been synchronized or verified as of this snapshot. Sync must remain blocked before credentials.
- Source-count, inventory-location, and full-catalog reconciliation are not yet implemented.
- No background cron enabled until shop identity, token scopes, tests and quotas are reviewed.
- For staging fallback/recovery, use the AppDeploy version list and apply_app_version.
- Do not promote to production until review, data isolation, credentials, and full data reconciliation pass.

Source of truth: GitHub PR #15 for code review; deployed AppDeploy revision must match reviewed source.
