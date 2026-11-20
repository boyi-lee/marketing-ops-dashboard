# Codex Instructions for Commerce Planning OS
1. Do not modify the parent repository homepage or main branch.
2. Shopify is strictly read-only. No mutations, inventory writes, price writes or order changes.
3. Preserve source identifiers, timestamps, currency, snapshot and calculation versions; no fabricated measurements.
4. Finance must be calculated in deterministic, tested code. AI explanations must never replace source calculations.
5. Missing data and insufficient history produce blocked/unverified status, not a confident forecast.
6. Plan drafts are platform-local only; require human review for approval.
7. Every change requires tests, contract checks, security checks, changelog and base-to-branch diff review.
8. Never commit secrets, customer PII, production data, or merchant access tokens.
9. If production dependencies are unavailable, document blockers and do not claim deployed or live.
