# P0 Diff / Deployment Ledger
Base: main. Branch: feat/commerce-planning-os-p0.
Expected changes: new commerce-planning-os/ subtree and isolated commerce-os-ci GitHub Action only.
Existing root index.html must remain byte-for-byte unchanged.
Verification: run Python unittest; inspect compare_commits file list and test workflow.
Deployment: NOT authorized until review gate; this code is a development slice, not a deployed application.
