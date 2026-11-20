# Campaign Planning OS | Local-first MVP
Initial isolated implementation for DESCENTE Taiwan; this branch does not modify existing Commerce Planning OS application.

## Quick start
Open `index.html` locally in a modern browser. Enter a revenue target, actual net revenue, elapsed days, ad spend, gross margin and costs. Values are planning assumptions until independently verified.

## Scope
- Working local KPI pacing and contribution financial calculator
- Guided quest/task workflow
- Theory explanations
- Local plan export
- Human review boundary

## Data connectors
Shopify, Meta Ads and Google Ads are **not authenticated from a local browser**. Production-grade daily sync requires server-side OAuth or API credentials, backend persistence, reconciliation and security review. ChatGPT connector permissions do not transfer to local code.

## Extended artifact
The separate downloadable full MVP bundle includes CSV SKU classification, a dedicated knowledge lab, Gantt prototype, schema and 8 tested business-rule cases.

## Business rules
ROAS does not equal ROI. Whole-store net revenue divided by ad spend is not ads-attributed ROAS. Estimated contribution is not net profit. Never count a duplicated listing as a second unit of physical inventory.
