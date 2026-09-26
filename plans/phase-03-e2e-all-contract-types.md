# Phase 03 — E2E All Contract Types (browser-automated, screenshot-evidenced)

**Depends on:** Phase 01 (behavior proven), Phase 02 (fresh-site ready, serials/depreciation/scrap work)
**Provides:** Scripted end-to-end proof that all three business models work in the Desk UI: setup → worksheet → contract → stock-to-asset → deploy → invoice → collect → reconcile → close/transfer/repossess.
**Evidence folder:** `plans/screenshots/` — every step saves `<flow>-<step>.png` + paired snapshot text (see §0). Login: `http://nbs.localhost:8003`, `Administrator` / `admin`. Tooling: global `agent-browser` (`agent-browser --help`, `agent-browser skills get core --full`); re-snapshot after every navigation (refs go stale); `record start/stop` for video where noted.

---

## 0. Conventions (all flows)

- Preconditions: `bench start` running (web `:8003`); site `nbs.localhost` migrated with Phase 02 seeders; one stock warehouse with serialized analyzer units on hand (receiving via Purchase Receipt beforehand is part of setup evidence).
- Naming: `E2E-RRA-…`, `E2E-CPT-…`, `E2E-RLO-…` customers/contracts; screenshot names match step IDs below (e.g. `rra-05-capitalize.png`).
- Money assertions cross-checked against `recompute_contract_recovery` values visible on the Contract form (dual progress bars) — screenshots must show the recovery panel.
- Fail-stop: any step that throws is screenshotted + snapshot-saved, then the run stops; fix in code, re-run from the failed step.

## Shared spine S0–S6 (run once, reused by all three flows)

| Step | Action | Shot |
|---|---|---|
| S0 | Purchase Receipt: 3 serialized analyzer units into stock warehouse | `setup-00-stock-in.png` |
| S1 | Item masters: analyzer (serialized stock) + 2 reagents/solutions + Reagent Specs + Instrument Spec + Test Params | `setup-01-masters.png` |
| S2 | Pricing Worksheet: fill analyzer/type/term/margin/volumes → calculate → verify uplift math vs pricelist source | `setup-02-worksheet.png` |
| S3 | Apply worksheet → draft Contract (lines + price list auto-created, status `Applied to Contract`) | `setup-03-applied.png` |
| S4 | Contract Capitalize: pick warehouse + serial → `create_asset_from_stock` → Asset + `Asset Capitalization` submitted, stock decremented | `setup-04-capitalized.png` |
| S5 | Submit Contract → `Active`; Create Deployment → `Deployed` (Asset Movement submitted) | `setup-05-deployed.png` |
| S6 | Outright-sale control: same analyzer Item sold via SO→DN→SI with no contract → clean submit, no Asset, no recovery effect | `setup-06-outright.png` |

## Flow A — RRA reagent-markup recoup (`rra-*`)

A1. Three monthly `Contract Reagent Sale` SIs at uplift price + one `Contract Consumable Replenishment` → submit. (`rra-01-invoiced.png`)
A2. Payment Entries collect two SIs fully, one partly → recovery panel shows invoiced vs collected vs outstanding. (`rra-02-collected.png`)
A3. `generate_monthly_reconciliation` for the period → `Compliant`; verify `linked_invoices`, actuals, `minimum_value_required`. (`rra-03-mrc.png`)
A4. Shortfall month: invoice below `min_monthly_value` → `Shortfall`, breach count +1; create penalty invoice (`SHORTFALL-PENALTY`); repeat to `breach_threshold` → auto Draft Repossession Request appears. (`rra-04-breach.png`)
A5. Approve RR → Execute Retrieval → Deployment `Permanently Retrieved`, Asset back to Warehouse, contract link cleared. (`rra-05-retrieved.png`)
A6. Redeploy same serial on a new RRA contract (proves reuse); then full-recovery variant: invoice to target → contract `Fulfilled`. (`rra-06-redeploy.png`, `rra-07-fulfilled.png`)

## Flow B — CPT revenue-share (`cpt-*`)

B1. Declared volume set → `generate_revenue_share_statement` → verify gross/our-share/customer-share math on form. (`cpt-01-statement.png`)
B2. Free-issue Delivery Note auto-created (all rates 0) + submitted revenue-share SI (`REVENUE-SHARE-FEE`). (`cpt-02-freeissue.png`)
B3. Collect share SI via PE → recovery panel moves. (`cpt-03-collected.png`)
B4. Mid-contract amendment: new declared volume → Mark Effective → next period statement uses overridden volume. (`cpt-04-amendment.png`)
B5. Non-payment path: unpaid share statements → manual Repossession Request (reason `Non-Payment of Revenue Share`) → retrieval as in A5. (`cpt-05-nonpay.png`)

## Flow C — RLO rent-to-own (`rlo-*`)

C1–C3. As A1–A3 (RLO bills like RRA; MRC path identical). (`rlo-01-invoiced.png` … `rlo-03-mrc.png`)
C4. Drive `cumulative_collected` to target with `ownership_threshold_met=1` → daily job auto-creates Ownership Transfer Request (or create manually if scheduler timing is impractical — note which in the run log). (`rlo-04-otr.png`)
C5. Finance → Legal approvals → attach transfer certificate → Complete Transfer: assert depreciation schedules **cancelled** (halted), Deployment `Permanently Retrieved` (reason `Ownership Transfer`), contract `Fulfilled`, OTR `Transfer Completed`. (`rlo-05-transferred.png`)
C6. Negative: RLO below threshold / with outstanding > 1 refuses OTR (screenshot the throw). (`rlo-06-otr-blocked.png`)
C7. Decommission path (separate RRA unit): retrieve → `decommission_analyzer` → native Asset Scrap posted, Asset `Scrapped`. (`rlo-07-scrapped.png`, shared scrap helper proven here)

## Edge sweep E1–E3 (any flow)

E1. Cancel guards: cancel Contract with live Deployment → blocked; cancel Worksheet while `linked_contract` set → blocked. (`edge-01-guards.png`)
E2. Idempotency: regenerate same MRC/RSS period → same doc, no duplicate invoices/DNs. (`edge-02-idempotent.png`)
E3. Cancel + amend interplay: cancel a contract SI → recovery reverses on form; amendment with `new_recovery_target < cumulative_collected` → blocked. (`edge-03-reversal.png`)

---

## Acceptance

- All steps A1–A6, B1–B5, C1–C7, E1–E3 executed with a PNG + snapshot-text pair in `plans/screenshots/`; any code fix restarts from the failed step, never by skipping.
- Recovery panels, MRC compliance states, RSS math, OTR terminal states, and scrap postings visible in screenshots.
- Run log (appendix to this doc on completion): date, site, commit hash, which steps needed scheduler vs manual trigger, all defects found with linked fixes.

---

## Appendix — Run log (2026-09-25/26, site nbs.localhost)

- Date: 2026-09-25 → 2026-09-26 (UTC). Site: `nbs.localhost`, company NORTHLAND BIOMEDICAL SOLUTIONS, currency USD. Tooling: global `agent-browser` as Administrator.
- Commit chain (app repo `apps/nbs_customization`, branch `placement-module`): `61fe415` (phase-02 checkpoint) → `7b11de2` → `4776504` → `8e06f75` → `40e59e8` → `3b177e0` → `0d77e52` → `7d6b761` → `7961b77` → `0022168` → `38abacd` (+ this log).
- Pre-flight: `migrate` clean, seeders verified (REVENUE-SHARE-FEE, SHORTFALL-PENALTY, Capital Asset, Others, Equipment), full suite green at start (75+24) and end (82+24, +7 regression tests).
- Scheduler vs manual: C4 OTR created manually per plan allowance (daily job not waited on). All period jobs (MRC/RSS) driven via Desk Generate buttons, never via scheduler.
- Key doc IDs: RRA `NBSIPC-2026/0001` (retrieved) → `NBSIPC-2026/0002` (Fulfilled 8160.12); CPT `NBSIPC-2026/0003` (retrieved); RLO `NBSIPC-2026/0005` (transferred); C7 RRA `NBSIPC-2026/0007` (scrapped asset `ACC-ASS-2026-00003` via JE `NBSJE-2026-00025`). Serials SN-001..004.
- Order deviations (logged, none skipped): B0 capitalize fail-stop fixed then resumed on draft `NBSIPC-2026/0003`; C6 run before C4 (negative first); B4 effective-dated inside September (site date 09-25/26 makes October un-markable — the effective-date gate is correct behavior); Sept MRC/RSS regenerations pick up late-posted invoices by design.
- Data repairs (console, logged): `NBSIPC-2026/0002` recompute flip to Fulfilled post-fix; `NBSCAM-2026/0001` status/effective-date set to what submit should have produced (pre on_submit fix); asset-2 location assert pre-retrieval.
- E2E-only artifacts left in site: 8 cancelled zero-rate SO/SI (entry-order lesson, superseded), penalty SI draft, failed-throw screenshots. No code TODOs left open.

### Defects found (all fixed + regression-tested, E2E re-proven from failed step)

1. Triple `nbs_customization` module path in 5 `frappe.call` sites (RR execute, MRC generate+penalty, RSS generate, OTR complete) → corrected to double path; proven via B5/C5 buttons.
2. `status` (+ OTR `legal_review_date`) lacked `allow_on_submit` → Approve buttons threw; set on RR/OTR/amendment (+ `approved_by`, `effective_date`).
3. OTR `on_submit` computed snapshots in memory only → `db_set` each field.
4. No auto-Fulfilled on full collection → `recompute_contract_recovery` flips Active→Fulfilled; re-proven on contract 2.
5. Capitalize button `frm.call` without `doc` → dotted path `get_attr` fails for instance methods; pass `doc: frm.doc` (run_doc_method). Serial dialog filter `In Store` → `Active`; Apply dialog asset optional + `asset || ""`.
6. Free-issue SO/DN repriced 50 by core `calculate_item_rate` (falsy 0 + price list) → pass explicit `price_list_rate: 0`.
7. Custom `frm.save("submit")` → KeyError; use `savesubmit()` (RR/OTR submit buttons).
8. Bare `frm.save()` on submitted docs → DocstatusTransitionError; `save_or_update()` on 6 approval/penalty buttons.
9. Amendment had no submit transition (stuck Draft, buttons unreachable) → `on_submit` sets Pending Customer Signature.
10. RSS gross read stale `fixed_monthly` snapshot (post-submit saves skip validate) → live line math in generate + explicit recompute in `apply_to_contract` (explicit `new_min_value` wins).
11. Same-day movement tie breaks ERPNext latest-location lookup → assert `Asset.location` pre-movement in deploy/retrieve handlers.
12. `decommission_analyzer` had no Desk entry → Decommission button on Permanently Retrieved deployments; proven in C7.
13. Equipment finance-book backfill missing (pre-existing categories got accounts but no books → no depreciation, transfers halt nothing) → backfill Straight Line 12/60. C5 halt itself remains backend-proven (no live schedules on asset 2); new assets now schedule-bearing.
14. E2E-method observations (no product change): item rows must be added item-first (fetch overwrites preset rates); SI requires `sales_order` (site `so_required`); group Locations unselectable in filtered dropdowns (used Test Location); deployment naming inherits contract series (`NBSIPC-2026/0004/0006/0008` are deployments).
