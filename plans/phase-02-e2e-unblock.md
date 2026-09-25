# Phase 02 — E2E Unblock (seed data, asset lifecycle, frontend gaps, permissions)

**Depends on:** Phase 01 (behavior proven; new tests here fail first where behavior is new)
**Provides:** Fresh-site readiness — billing items exist, amendment logic lives in its controller, serial-mandatory + depreciation-halt + scrap flows work, Asset UI wired, permissions verified, outright-sale path regression-tested.
**Locked decisions:** (1) Serial mandatory for every placement analyzer. (2) RLO transfer halts/cancels the depreciation schedule. (3) Decommission = native ERPNext Asset Scrap. (4) Auto-repossession gated by `breach_threshold` consecutive breaches (already implemented in `monthly_reconciliation.py:126-150`; this phase adds tests + default threshold documentation).

---

## Objective

Close every small-but-blocking gap found in the audit so Phase 03 E2E can run on a migrated site without manual seeding or dead-end buttons. Principle: reuse ERPNext natives (`Asset Capitalization`, `Asset Movement`, `Asset Depreciation Schedule`, Asset Scrap), extend only via our custom fields and controllers.

---

## 1. Seed billing + capital items (`nbs_customization/setup.py:492-557`)

Unpause and harden (idempotent, `db.exists` guards kept):

| Seeder | Item | Spec |
|---|---|---|
| `_ensure_brand_others()` | Brand `Others` | Prerequisite for all three items |
| `create_revenue_share_fee_item()` | `REVENUE-SHARE-FEE` | `item_group Services`, `is_stock_item=0` (consumed by `revenue_share_statement.py:10`) |
| `create_shortfall_penalty_item()` | `SHORTFALL-PENALTY` | `item_group Services`, `is_stock_item=0` (consumed by `monthly_reconciliation.py:187`) |
| `create_nbs_capital_asset_item()` | `Capital Asset` | `is_fixed_asset=1`, `is_stock_item=0`, `asset_category=Equipment`, `item_group Products` — verify `Asset Category Equipment` exists first; if absent, create it (depreciation defaults: straight line, company books) rather than failing migrate |

Wire all four into `after_migrate()` (replace PAUSED block). Remove the xfail/skip marks added in Phase 01 §3–§4. Tests: new `tests/test_placement_setup.py` — run `after_migrate()` twice, assert items exist, no duplicates; assert fee-item SIs submit on a migrated site.

## 2. Amendment controller owns its logic

Finish the Phase 01 refactor if not already landed:

- `.../doctype/contract_amendment/contract_amendment.py` — `ContractAmendment.apply_to_contract()` contains the former `tasks._apply_amendment_to_contract` body (`tasks.py:106-131`): volume→lines, `new_min_value`, `new_share_pct`, `new_pricing_worksheet`, `new_recovery_target`, save, flip `Effective`. Add field-level validation (amendment lines reference items belonging to the contract analyzer; `new_recovery_target >= cumulative_collected` guard so history is never invalidated).
- `tasks.daily_process_amendments` + `controllers/placement/amendment.mark_effective` become thin delegating wrappers.
- Contract JSON: confirm amendment-link fields (`new_declared_volume`, `new_min_value`, `new_share_pct`, `new_pricing_worksheet`, `new_recovery_target`, `status`, `effective_date`) match what the controller reads — rename at most once, with a `patches.txt` migration if renamed.

## 3. Stock → asset path: serial-mandatory + native lifecycle

All in `instrument_placement_contract.py:create_asset_from_stock:93-169` and `ownership_transfer_request.py:complete_transfer:109-156` + deployment:

1. **Serial mandatory** — `create_asset_from_stock` keeps requiring a real `Serial No` (`In Store`, matching `analyzer_pid` + warehouse); add explicit throws when the analyzer Item lacks `has_serial_no=1` and when `serial_no` is blank on Capitalize/Deploy. Analyzer Items created via Item form must be serialized stock items (`is_stock_item=1`); the generic `Capital Asset` target stays non-stock fixed asset (no change).
2. **Depreciation halt on RLO transfer** — in `complete_transfer`, after setting `Transfer Completed`: fetch the linked `Asset Depreciation Schedule`(s) for the asset and **cancel** all non-cancelled schedules (native cancel, not delete — audit trail preserved), then `db_set` the Asset status per native flow. Snapshot logic (`analyzer_recovery_collected`, NBV, gain/loss in `_validate_submit_requirements:42-64`) is unchanged; halt happens exactly once (guard on re-entry: completed OTRs are terminal).
3. **Decommission = Asset Scrap** — add whitelisted `decommission_analyzer(asset_name, reason)` (location TBD: `controllers/placement/contract.py` or deployment controller) that requires the Asset to have no Deployed deployment and no Active contract link, then invokes the native Asset scrap flow (scrap Journal Entry + Asset status `Scrapped`). Deployment `Permanently Retrieved` with reason mapping preserved for repossession/transfer paths; scrap is the terminal state for unusable units.
4. **Redeploy** stays as-is (`make_deployment` on a new contract reuses the same Asset/serial; `Analyzer Deployment` history per asset is the movement trail) — add a test proving one serial serves two sequential contracts.

## 4. Frontend gaps

- `nbs_customization/public/js/asset.js` (currently 0 lines, wired in `hooks.py` `doctype_js`) — display placement state on Asset: `custom_current_placement_contract` link, `custom_current_deployment_status` badge, serial; read-only when linked to an Active contract (guard against manual edits that bypass deployment transitions). `bench build --app nbs_customization` after editing.
- Add `revenue_share_statement_list.js` + `contract_amendment_list.js` status indicators (match existing `*_list.js` color conventions).
- Fix dead branch in `contract_amendment.js:56` (references non-existent `_mark_effective_btn` df) — wire Mark Effective to the real button/eligibility check per `frontend-09 §4.3`.
- Contract form: surface `breach_threshold`/`grace_period_days` defaults with help text (documents decision 4 in-UI).

## 5. Permissions, patches, fixtures

- Set DocType permissions (all 9 placement DocTypes + child tables): Sales Manager / Accounts Manager full; Sales User submit-level on Contract/Worksheet/Reconciliation/RSS; read for Auditor role. Verify via `has_permission` smoke in `test_placement_setup.py`.
- `patches.txt`: add post-sync patch only if a field rename or backfill is needed (§2, Equipment category); otherwise record "no placement patch required" decision in the commit message.
- Fixtures: keep placement DocTypes un-fixtured (transactional); Custom Fields backing SO/DN/SI/Item/Asset placement links stay in `fixtures/custom_field.json` — re-export after any field change (`bench --site nbs.localhost export-fixtures`).
- Outright-sale regression test: serialized analyzer sold via standard SO→DN→SI with **no** contract link → submits cleanly, stock decrements, no Asset created, no recovery side effects. (Proves stock duality: same Item sells outright or capitalizes onto a contract.)

---

## Acceptance

- Fresh `bench --site nbs.localhost migrate` → fee/capital items exist; Capitalize-from-stock works with a real serial and refuses without one.
- RLO `complete_transfer` cancels depreciation schedules; scrap path scraps natively; one serial provably redeploys across two contracts.
- `asset.js` renders placement state; all lifecycle doctypes have list indicators; amendment dead branch gone.
- Full placement test suite (Phase 01 + new §1/§3/§5 tests) green; `pre-commit run --all-files` clean.
