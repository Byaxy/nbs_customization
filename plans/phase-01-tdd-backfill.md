# Phase 01 — TDD Backfill (prove existing placement behavior)

**Depends on:** backend-01..12, frontend-03..09 (code exists on `placement-module`, commit `4474168`)
**Provides:** Real behavioral tests for every placement controller/util whose test file is currently stub or smoke-only. No production-code changes except test-driven fixes (assert the behavior, fix only what is provably broken).
**Locked decisions:** Serial tracking mandatory for every placement analyzer; N consecutive breaches (`contract.breach_threshold` + `consecutive_breach_count`, see `monthly_reconciliation.py:126-150`) gate auto-repossession.

---

## Objective

Turn 7 stub/smoke test files into genuine TDD coverage for the full money-and-asset path: recovery rollup → deployment side effects → monthly reconciliation → revenue-share → repossession → ownership → amendment → scheduled jobs. Out of scope: new features (seed items, depreciation halt, scrap, reports — Phases 02/04), E2E browser flows (Phase 03).

---

## 0. Shared fixture builder (write first, reuse everywhere)

Create `nbs_customization/tests/placement_fixtures.py` with helpers (all names prefixed `_TST-PL`, `ignore_if_duplicate=True`, `IntegrationTestCase` rollback so no manual cleanup):

| Helper | Builds |
|---|---|
| `make_analyzer()` | Stock Item (serialized, `has_serial_no=1`) + `Analyzer Type` + `Test Parameter` + `Instrument Specification` |
| `make_reagent(role="Test Reagent")` | Stock Item + `Reagent Specification` (`default_cogs_per_pack`, `default_tests_per_pack`) |
| `make_customer()` | `Customer` Company |
| `make_worksheet(analyzer, reagent, contract_type="RRA", status="Approved")` | Submitted-ready `Instrument Pricing Worksheet` (follow `test_instrument_pricing_worksheet.py` setup) |
| `make_contract(...)` | Draft `Instrument Placement Contract` with reagent + consumable lines, worksheet link, dates, `breach_threshold`, `grace_period_days` |
| `make_serial(analyzer, warehouse)` | `Serial No` in `In Store` state for Capitalize-path tests |

Refactor existing placement test setups to use these helpers only where it reduces duplication — do not churn passing tests (`test_instrument_specification`, `test_reagent_specification`, `test_valid_items`, `test_instrument_pricing_worksheet`, `test_instrument_placement_contract` stay green throughout).

Run per-file:
```bash
bench --site nbs.localhost run-tests --app nbs_customization --module nbs_customization.tests.<module> --test <TestClass.test_method>
```

---

## 1. `nbs_customization/utils/placement/test_recovery.py` (3× `pass` → real)

Target: `utils/placement/recovery.py:recompute_contract_recovery` + hooks in `controllers/placement/sales_invoice.py`, `payment_entry.py`.

- `test_recompute_updates_contract` — RRA contract with `total_recovery_target=12000`; two submitted SIs (`custom_instrument_placement_contract` set, `custom_counts_toward_recovery=1`, totals 4000/2000, one partly paid); assert `cumulative_invoiced=6000`, `cumulative_collected`, `outstanding_on_contract = target − collected`, both pcts.
- `test_recompute_zero_target` — target 0 → pcts 0, no `ZeroDivisionError`.
- `test_payment_entry_triggers_recompute` — PE against a contract SI updates `cumulative_collected`/`outstanding_on_contract`; SI cancel reverses; SI with `custom_counts_toward_recovery=0` ignored.
- `test_free_issue_excluded` — CPT free-issue DN-rate-0 SI (if flagged non-recovery) does not inflate `cumulative_invoiced`.

## 2. `.../doctype/analyzer_deployment/test_analyzer_deployment.py` (3× `pass` → real)

Target: `analyzer_deployment.py:8-110`.

- `test_deployed_sets_asset_status` — Deployed sets `Asset.custom_current_deployment_status=Deployed` + `custom_current_placement_contract`, creates submitted `Asset Movement` (source storage → site).
- `test_temporary_retrieval_keeps_contract_link` — Temporarily Retrieved → status `Warehouse`, contract link retained.
- `test_permanent_retrieval_clears_contract` — Permanently Retrieved → status `Warehouse`, contract link cleared, second `Asset Movement` created. (Serial No mandatory: deployment requires linked Asset with `custom_serial_no` set.)

## 3. `.../doctype/monthly_reconciliation/test_monthly_reconciliation.py` (1 smoke + 3× `pass` → real)

Target: `monthly_reconciliation.py:generate_monthly_reconciliation`, `_compute_compliance:126-150`, `create_penalty_invoice`, `_auto_create_repossession_request`.

- `test_generates_and_aggregates` — RRA contract + two SIs in period (`Contract Reagent Sale`, `Contract Consumable Replenishment`) → reagent/consumable/total actuals + `linked_invoices` rows; SI outside period excluded; CPT contract raises.
- `test_shortfall_increments_breach` — total < `min_monthly_value`, grace expired → `Shortfall`, `consecutive_breach_count = previous + 1`.
- `test_grace_period_holds_count` — within `grace_period_days` of `period_end` → `Grace Period`, count unchanged.
- `test_threshold_auto_creates_repossession` — `new_count >= breach_threshold` → Draft `Repossession Request` (reason `Minimum Purchase Breach`, breach counts copied); below threshold → none; existing non-Closed RR → no duplicate; idempotency: regenerate same contract+period updates in place.
- `test_penalty_invoice_guards` — Compliant/Grace raises; Shortfall creates SI (`SHORTFALL-PENALTY` — xfail/skip until Phase 02 seeds the item; mark clearly).

## 4. `.../doctype/revenue_share_statement/test_revenue_share_statement.py` (1 smoke + 4× `pass` → real)

Target: `revenue_share_statement.py` (`generate_revenue_share_statement`, `_resolve_declared_volume`, free-issue DN + SI creation).

- `test_statement_and_invoice_created` — CPT contract + declared volume → gross/our-share/customer-share math, free-issue DN (all rates 0), submitted revenue-share SI (`REVENUE-SHARE-FEE` — xfail/skip until Phase 02 seeds the item).
- `test_amendment_volume_overrides` — Effective amendment inside period overrides `monthly_test_volume` sum.
- `test_idempotent` — regenerate same contract+period returns same statement, no duplicate DN/SI.
- `test_rra_rejected` — non-CPT contract raises.

## 5. `.../doctype/repossession_request/test_repossession_request.py` + `.../doctype/ownership_transfer_request/test_ownership_transfer_request.py`

- Repossession: submit → `Pending Approval`; illegal jump (Draft→Approved) raises; `execute_retrieval` requires Approved (raises otherwise), flips Deployment to `Permanently Retrieved` with reason mapping + retrieval fields, sets RR `Analyzer Retrieved`.
- Ownership: non-RLO contract raises on insert; RLO below threshold / outstanding > 1 raises; eligible RLO allows Draft; `complete_transfer` requires Approved + `transfer_certificate`, suspends depreciation schedule (assert schedule cancelled — implements Phase 02 behavior; write test here, land with Phase 02 code if not yet present), sets contract `Fulfilled`, OTR `Transfer Completed`.

## 6. `.../doctype/contract_amendment/test_contract_amendment.py` (0 methods → full)

Refactor first: move `tasks._apply_amendment_to_contract` (`tasks.py:106-131`) into `ContractAmendment.apply_to_contract()` controller method; `tasks.daily_process_amendments` and `controllers/placement/amendment.mark_effective` delegate to it (thin wrappers, no logic duplication — fixes the stub-controller smell; `contract_amendment.py` is currently 9-line `pass`).

- `test_apply_volume_updates_lines` — `new_declared_volume` pushes to all reagent lines (`monthly_test_volume` + `min_monthly_qty` recompute).
- `test_apply_value_share_worksheet_target` — `new_min_value` / `new_share_pct` / `new_pricing_worksheet` / `new_recovery_target` applied; amendment flips `Effective`.
- `test_daily_job_applies_due_only` — Approved + `effective_date <= today` applied; future-dated untouched.

## 7. `nbs_customization/tests/test_tasks.py` (smoke → behavior)

Keep importability checks; add: monthly jobs generate MRC only for Active RRA/RLO and RSS only for Active CPT (wrong-type contracts skipped); daily amendment job applies due amendments; daily RLO check creates OTR only when `ownership_threshold_met=1` and no non-Closed OTR exists; per-contract failures logged, not raised (one bad contract does not abort the batch).

---

## Acceptance

- Zero `pass`-only test methods in placement scope; every B6–B12 behavior has ≥1 asserting test.
- `bench --site nbs.localhost run-tests --app nbs_customization` green (pre-existing suites unbroken).
- `ruff check nbs_customization && ruff format --check nbs_customization` clean; files <300 lines, tabs per repo config.
- Known xfails explicitly marked: penalty-fee and revenue-share-fee tests pending Phase 02 seed items.
