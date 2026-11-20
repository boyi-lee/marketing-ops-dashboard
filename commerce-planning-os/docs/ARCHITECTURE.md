# Module and Interface Architecture (draft)
M01 read-only Shopify Admin GraphQL adapter -> M04 raw snapshots -> M03 product master -> M05–M08 deterministic analytics -> M09 knowledge + M10 Codex MCP -> M11 plans -> M12 dashboard.
M02 imports purchase orders and effective-dated cost independently; unconfirmed inbound must not count as stock.
M13 identity and M14 operations apply across modules.
M01 must not expose Shopify mutation endpoints. M10 may create local plan drafts, but no Shopify writes.
Source-of-truth: Shopify product/order/inventory; separate procurement for incoming stock; accounting for validated costs; this OS for plan versions.
All API and database data must include store-scoped identity, currency, source provenance, snapshot ID, rule version, validation state.
Pre-production gates: actual API credentials with read scopes only; auth isolation; PostgreSQL migrations; worker retry; restore rehearsal; CI test pass; staging smoke test.
This scaffold is not proof these production gates are complete.
