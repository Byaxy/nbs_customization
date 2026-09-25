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
