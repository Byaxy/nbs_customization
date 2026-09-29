# Backend-18 — Check Clearing Accounts under Receivable/Payable Groups

## Context / Problem

`_ensure_check_clearing_setup()` (setup.py) creates the two cheque clearing accounts
per company under the generic balance-sheet groups:

- `Cheques in Transit - Inward` (Asset) under **Current Assets**
- `Cheques in Transit - Outward` (Liability) under **Current Liabilities**

For correct balance-sheet presentation the inward account should sit under
**Accounts Receivable** (it represents receivables collected but not yet cleared) and
the outward account under **Accounts Payable** (it represents payables paid but not yet
cleared). Verified example — NBS company:

- `Cheques in Transit - Inward - NBS` parent was `Current Assets - NBS`
- `Cheques in Transit - Outward - NBS` parent was `Current Liabilities - NBS`

## Decisions

1. Target parents are the company's **Accounts Receivable / Accounts Payable group
   accounts**. ERPNext v16 Company has no `receivables_group`/`payables_group` fields,
   so the groups are resolved as the **parents of `default_receivable_account`
   (`Debtors - NBS` → `Accounts Receivable - NBS`) and `default_payable_account`
   (`Creditors - NBS` → `Accounts Payable - NBS`)**. Falls back to the standard chart
   names `["Accounts Receivable", "Debtors"]` / `["Accounts Payable", "Creditors"]`,
   then to Current Assets / Current Liabilities so nothing is skipped on odd charts.
2. The fix must be **idempotent for existing installs**: accounts already created under
   Current Assets/Current Liabilities must be **relocated** (parent updated), not left
   behind — `_ensure_account` gains relocation.
3. Account **names are unchanged**, so existing GL entries, the `Check` Mode of Payment
   wiring (`clearing_account_inward`/`clearing_account_outward`), and the `Cheques in
   Transit` report are untouched. NSM reindex on save recomputes group rollups.

## Implementation

### 1. `apps/nbs_customization/nbs_customization/setup.py`

- Add `_receivable_payable_groups(company)` returning `(receivable, payable)` group
  names (parent of default receivable/payable account, with fallbacks).
- `_ensure_account`: when the account already exists, if its `parent_account` differs
  from the target, load it, set `parent_account`, save with `ignore_permissions=True`;
  return the existing name.
- `_ensure_check_clearing_setup`: resolve `receivable`/`payable` via the new helper
  (falling back to Current Assets/Current Liabilities) and pass them as parents for
  inward/outward respectively.

### 2. `apps/nbs_customization/nbs_customization/tests/test_check_clearing.py`

- Add `test_clearing_accounts_under_receivable_payable_groups` asserting inward's parent
  is `Accounts Receivable - _TC` and outward's parent is `Accounts Payable - _TC`.

## Verification

1. `ruff check` on `setup.py` and `test_check_clearing.py`.
2. `bench --site test-site run-tests --app nbs_customization --module nbs_customization.tests.test_check_clearing`
3. `bench --site nbsolutions.localhost migrate` (runs `after_migrate` → relocation).
4. Confirm via query: inward parent = `Accounts Receivable - NBS`, outward parent =
   `Accounts Payable - NBS`, GL entries against both accounts still intact (4 rows).