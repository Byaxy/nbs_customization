# Phase 04 — Revenue & Status Reports (all three)

**Depends on:** Phase 01 (numbers proven), Phase 02 (fee items + lifecycle complete), Phase 03 (figures validated in-UI)
**Provides:** Three query reports under the inner module (`nbs_customization/nbs_customization/report/`): contract status + recovery %, monthly revenue flow, asset tracking. No new business logic — every figure ties to `recompute_contract_recovery`, MRC, or RSS outputs.
**Locked decisions:** Serial mandatory (asset report keys on `custom_serial_no`); depreciation halt + scrap states surface in the asset report; breach-threshold counts surface in the status report.

---

## Objective

Give management the three views requested: (a) where every contract stands and how much money is recovered, (b) how much placement revenue moves per period across RRA/RLO/CPT, (c) where every analyzer is and what happened to it. Follow the `backend-14` day-close report pattern (filters → columns → deterministic SQL/qb, no N+1); add tests mirroring `test_daily_income_and_expense.py:278-350` (report and any dashboard card logic kept in sync).

---

## R1. Contract Status + Recovery % (`placement_contract_status`)

Filters: Company, Contract Type (RRA/RLO/CPT), Contract Status (Draft/Active/Fulfilled/Breached/Terminated/Expired), Customer.

Columns (one row per contract): contract, customer, type, status, asset + serial, start/end, `total_recovery_target`, `cumulative_invoiced`, `cumulative_collected`, `outstanding_on_contract`, `recovery_pct_invoiced`, `recovery_pct_collected`, `min_monthly_value`, `consecutive_breach_count`, latest MRC period + `compliance_status`, linked OTR/RR (if any).

Source: `tabInstrument Placement Contract` left-joined to latest `tabMonthly Reconciliation` / open `tabRepossession Request` / non-Closed `tabOwnership Transfer Request`. Recovery columns read straight off the contract (maintained by `recompute_contract_recovery`) — never recomputed in the report. Status color mapping reuses `instrument_placement_contract_list.js` indicators.

## R2. Monthly Revenue Flow (`placement_monthly_revenue`)

Filters: Company, Period range (YYYY-MM), Contract Type.

Columns (one row per contract × period): period, contract, type, invoiced-this-period (submitted SIs with `custom_counts_toward_recovery=1` in period), collected-this-period (allocated PE amounts in period against those SIs — define as `grand_total − outstanding` delta captured at period end; document the exact definition in the report help), MRC compliance (RRA/RLO) or RSS share amount (CPT), running cumulative collected vs target.

Source: `tabSales Invoice` (+ `tabPayment Entry` allocations) constrained to placement-linked docs; MRC/RSS tables for compliance/share columns. Totals row per period + grand total. Must reconcile: sum of period invoiced per contract over all periods = `cumulative_invoiced` (assert in tests).

## R3. Asset Tracking (`placement_asset_tracking`)

Filters: Company, Deployment Status (Warehouse/Deployed/Under Service/Temporarily Retrieved/Permanently Retrieved/Scrapped), Contract, Analyzer Item.

Columns (one row per placement Asset): asset, analyzer item, `custom_serial_no`, current status, current contract, customer site / storage location, deployment history (count + latest deployment + dates), originating contract (first Capitalize), terminal state (`Transfer Completed` / `Scrapped` / active), NBV (`value_after_depreciation`), depreciation schedule state (Active/Cancelled — proves decision 2).

Source: `tabAsset` (placement-linked: `custom_current_placement_contract` or `custom_serial_no` present) joined to `tabAnalyzer Deployment` history + `tabAsset Movement` + OTR/scrap records. Scrapped assets remain listed (filterable) — decommission never hides history.

---

## Tests (`tests/test_placement_reports.py`)

Fixture: one RRA (2 SIs, 1 PE, 1 MRC Shortfall), one CPT (1 RSS + share SI), one RLO (transferred, schedule cancelled), one retrieved-then-redeployed serial, one scrapped asset. Assert: R1 recovery columns equal contract fields; breach count + compliance shown; R2 period sums tie to `cumulative_invoiced`; R3 serial appears twice in deployment history (redeploy), scrap + transfer-completed states listed with correct NBV/schedule flags. Keep report logic in pure functions (`get_data(filters)`) so tests call them without HTTP.

---

## Acceptance

- All three reports run from Desk search on `nbs.localhost` with filters working; figures tie to contract/MRC/RSS on fixture data (no silent recomputation).
- `test_placement_reports.py` green; sums reconcile across R1↔R2.
- No report exceeds one focused query module (<300 lines each); shared column/format helpers in a single `report/placement_common.py` if duplication appears (third use → abstract, per `code-style`).
