# Gate checklist and disposition
G1 contract & provenance: P0 fixture contract checks PASS; real Shopify reconciliation NOT TESTED.
G2 deterministic calculations: P0 core unittest tests in CI; P&L FULL not implemented.
G3 integration: cross-tenant same-variant identity checked; actual API/MCP/worker integration NOT TESTED.
G4 security: no Shopify mutation code in this module; production auth/secret scanning/restore NOT TESTED.
G5 business strategy: no production strategy approval or historical campaign uplift evaluation yet.
Promotion into main or staging is BLOCKED until reviewers confirm gate evidence. No automatic merge or deployment.
Rollback for this isolated branch: close PR / revert merge commit; production DB rollback requires validated migration and backup.
