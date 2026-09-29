# Phase 05 — Polish & Release (print, workspace, lint, merge)

**Depends on:** Phases 01–04 (feature complete, tested, reported, E2E-evidenced)
**Provides:** Shippable `placement-module`: print formats, Desk discoverability, clean lint, full-suite green, merge checklist.

---

## Objective

Close the remaining audit gaps (no placement print formats, no workspace/page, lint unverified) and define done for merging `placement-module` → `main`.

---

## 1. Print formats (`nbs_customization/nbs_customization/print_format/`)

New (Jinja, reuse existing format conventions from `sales_invoice`/`loan_waybill`):

| Format | For | Must show |
|---|---|---|
| `instrument_placement_contract` | Contract | parties, analyzer + serial, term, type terms, reagent/consumable lines (standard vs contract price, uplift), targets, recovery summary, signatures block |
| `analyzer_deployment` | Deployment | asset/serial, contract, site, dates, accessories (`deployment_accessory`), retrieval fields when set |
| `revenue_share_statement` | RSS | period, declared volume, gross/share math, linked free-issue DN + share SI |

Verify each via Print Preview (PDF pipeline touches `print_designer.pdf` — see repo Gotchas; manual preview required, no automated PDF assert). MRC reuses the contract format's financial block — no separate MRC format unless users ask.

## 2. Desk discoverability

- Workspace Sidebar: add placement group (Contract, Worksheet, Deployment, Reconciliation, Revenue Share, Repossession, OTR, Amendment + R1–R3 reports) after `Sales Invoice` in Selling sidebar, following `setup.py` `_inject_*` pattern (idempotent, committed).
- Confirm every lifecycle doctype has a working `*_list.js` (Phase 02 added the two missing ones; re-verify Contract, Worksheet, MRC, Deployment, Repossession, OTR here).
- No new `page/` dashboard — code-driven indicators (progress bars, status colors) plus R1–R3 reports are the surface (documents the "no placement page" audit finding as intentional).

## 3. Lint, format, full suite

```bash
# from apps/nbs_customization/
pre-commit run --all-files
ruff check nbs_customization && ruff format --check nbs_customization
# from bench root (/home/byaxy/frappe/nbs_customization)
bench --site nbs.localhost run-tests --app nbs_customization
bench build --app nbs_customization
```

Rules: `ruff` line-length 110, `py314`, tabs for `*.py/*.js/*.vue`, spaces for doctype JSON (repo config). Note the pre-commit gap: `files: "nbs_customization.*"` only lints inside `apps/nbs_customization/nbs_customization/` — bench-level or `sites/` edits need manual review. Fix all findings before merge; no `noqa`/exclusions without a comment explaining why.

## 4. Merge checklist (placement-module → main)

- [ ] Phases 01–04 acceptance criteria all met (link test runs + screenshot folder + report tests).
- [ ] `git status` clean; only intended files staged (`git diff` reviewed); no secrets; commit messages match repo style.
- [ ] `bench --site nbs.localhost migrate` + `clear-cache` clean on a fresh restore (seeders idempotent, no placement patch failures).
- [ ] Check-clearing + daily-income suites still green (no cross-feature regression from shared SO/DN/SI/PE hooks).
- [ ] Plan docs updated with run-log appendices (Phase 03 evidence log, report reconciliation notes).
- [ ] PR description lists the 4 locked decisions (serial-mandatory, depreciation-halt, scrap-decommission, breach-threshold) for reviewer context.
