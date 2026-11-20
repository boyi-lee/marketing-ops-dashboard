# P1 inbound and cost data contracts

Procurement systems provide inbound lines. Finance systems provide costs.
Neither file is written back to Shopify. Every row must contain store scope,
document ID, external SKU or Shopify variant GID and timezone-aware timestamps.

Import workflow:
1. Human uploads CSV to protected staging intake.
2. Strict validate **all rows**; a single failure blocks the batch.
3. Map external SKU to canonical store-specific variant where available.
4. Require explicit reconciliation and signoff before cost is eligible for P&L.
5. Store immutable source file hash, import approval and original document.
6. Incoming stock remains separate from on-hand; tentative orders cannot
   count as confirmed sales supply.

Security limitations: These functions only parse and validate in memory.
No authenticated file upload, object storage, malware scanning, provenance
signature, database persistence or enterprise authorization has been deployed.
