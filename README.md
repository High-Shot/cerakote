# Cerakote Ops

One site, three pages, one shell: https://high-shot.github.io/cerakote/

| Page | Source | What it covers |
|---|---|---|
| `sales/` | High-Shot/NIC `data/weeks/*.json` + this repo's `data/budgets`, `data/pacing` | Weekly sales, ads, NTB by market, plus monthly ad budget pacing |
| `health/` | High-Shot/INTL `data/snapshots/*.json` (account and case items only) | Account health, policy and compliance issues, feedback, Seller Support cases |
| `inventory/` | High-Shot/INTL `data/q4/*.json` + `q4/files/` | Q4 stock projection, lost sales, ship-by schedule, Send to Amazon files |

This repo only renders. The NIC and INTL repos stay the data pipelines and keep publishing their own pages, so nothing upstream changes.

```
pages/            page templates (sales.html, health.html, inventory_body.html + inventory_app.js, logo.svg)
scripts/build.py  NIC + INTL data -> sales/, health/, inventory/ (shared header, nav and styles injected here)
scripts/pacing.py writes data/budgets/<month>.json and data/pacing/<month>.json
RUNBOOK.md        the Monday/Thursday 08:45 CT refresh
```

Budget pacing uses the budget sheet's column I logic: spend to date / (budget x days elapsed / days in month).
Local build: `python3 scripts/build.py --nic ../NIC --intl ../INTL`
