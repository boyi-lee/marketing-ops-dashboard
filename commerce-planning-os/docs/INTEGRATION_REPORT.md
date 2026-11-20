# P0 Integration and Security Evidence

### New runnable scope
- Fixture Shopify-equivalent product records -> SQLite -> inventory summary API -> campaign draft -> query.
- Multi-store scoped access and draft-only write policy.
- Confirmed inbound only; future and tentative inventory excluded.
- Duplicate syncing and old snapshot suppression.
- Atomic invalid batch validation; SQLite process restart persistence.
- No Shopify write route in this isolated app.

### CI
Run: `cd commerce-planning-os && python3 -m unittest discover -s tests -v`.
The existing parent `index.html` is unchanged, as verified by comparing base/main with feature branch.

### Threat model limitations
- The actor object is injected by tests, not cryptographically authenticated.
- SQLite is a fixture store, NOT multi-user production PostgreSQL.
- Static route/credential denylist does not establish a comprehensive security audit.
- Contracts have schema declaration but no external runtime JSON Schema validation.
- This is a transport-independent API simulation, not a live HTTP deployment.
- Shopify/MCP connectors, AI Skill quality evaluation, backups and staging remain outstanding.

Release state: **BLOCKED** until actual data, auth and deployment gates are satisfied.
