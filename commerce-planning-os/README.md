# Commerce Planning OS (isolated P0 development slice)
Scope: read-only Shopify ingestion adapters (future), verified merchandise analytics, KPI scenario checks and campaign draft planning. **Never write to Shopify.**
The existing site in the repository root is not modified.

## Run
Python 3.11+ required; no third-party dependencies:
```bash
cd commerce-planning-os
python3 -m unittest discover -s tests -v
```

## Status
P0 scaffold and deterministic core are implemented here. Real Shopify, PostgreSQL, RBAC, Codex MCP, deployments, live P&L and production-grade security are **NOT yet implemented or verified**.
Issues #1–#14 track the modules. No real brand figures in fixtures.

## Modules
M01 Shopify; M02 Inbound; M03 Product; M04 Quality; M05 Inventory; M06 Lifecycle; M07 Profitability; M08 KPI; M09 Knowledge; M10 Codex; M11 Campaign; M12 Dashboard; M13 Identity; M14 Operations.
