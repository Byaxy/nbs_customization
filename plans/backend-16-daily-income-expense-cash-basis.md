# Backend-16 — Cash-Basis Income/Expense (Payment Entry / Journal Entry)

## Context / Problem

The Daily Income and Expense report (B14) and the dashboard page (B15) currently report
income and expenses on the **accrual basis**: `get_income`/`get_expenses` read GL Entries
on Income/Expense accounts for the selected date. As a result:

- Income rows = Sales Invoices (receivable, not cash received).
- Expense rows = Purchase Invoices (payable, not cash paid).

The user wants the report to show **actual money movement**:

- **Income** = money actually received → always a **Payment Entry** against a Sales
  Invoice (row = PE number, amount, mode of payment, linked invoice, party/customer).
- **Expenses** = money actually paid, which happens in two ways:
  1. a **Payment Entry** against a Purchase Invoice, or
  2. a **direct payment** recorded as a **Journal Entry** through the NBS Expense module.
  - Party/Payee = supplier name (PE) or the Payee from the Expense doc (JE).
  - Linked column = Purchase Invoice (PE) or Expense No (JE).
  - Add a visible **Type** column to distinguish PE vs JE rows.
  - Amount + Date columns kept.
- The Account column is removed from the income/expense tables.

## Verified Live Data (nbsolutions.localhost)

**Income — 2026-06-12 (Receive PEs):**

| PE | Party | Mode | Base Paid | Linked SI | Unallocated |
|----|-------|------|-----------|-----------|-------------|
| ACC-PAY-2026-00022 | GIMS HOSPITAL | Bank Transfer | 50.00 | — | 50.00 |
| ACC-PAY-2026-00023 | ST.JOSEPH CATHOLIC HOSPITAL | Cash | 2,341.56 | NBSINV-2026/06/0004 | 0 |
| ACC-PAY-2026-00024 | GIMS HOSPITAL | Bank Transfer | 114.90 | NBSINV-2026/06/0005 | 0 |

**Expenses — 2026-08-05 (3 Pay PEs + 2 direct JEs):**

- ACC-PAY-2026-00029 — Alltest Biotech (Cheque) 50 → PI ACC-PINV-2026-00007-1
- ACC-PAY-2026-00030 — Landlord Office (Cash) 300 → PI ACC-PINV-2026-00012
- ACC-PAY-2026-00031 — Erba Diagnostics (Cash) 300 → PI ACC-PINV-2026-00013
- ACC-JV-2026-00044 — NBSEXP-2026/08/0004 Rent March / Payee Landlord Mike (Cash) 100
- ACC-JV-2026-00045 — NBSEXP-2026/08/0006 transport / Payee Bike guy (Cash) 50

## Decisions (confirmed with user)

1. Include income PEs with no linked invoice (advance/unallocated) — blank Linked Invoice cell.
2. Expense PE Party/Payee column = supplier name (`pe.party_name`).
3. Drop per-account summary rows; show PE/JE detail rows + totals only.
4. Add a visible **Type** column (Payment Entry / Journal Entry) in the expenses table.
5. Date filter = `posting_date` of the PE/JE (money movement date).
6. JE expense rows are only those produced by the Expense module (linked via `tabExpense.journal_entry`).
7. Amounts use company-currency base: `base_paid_amount` (PE) / `Expense.amount` (JE).

## Implementation

### 1. `apps/nbs_customization/nbs_customization/nbs_customization/report/daily_income_and_expense/daily_income_and_expense.py`

**Rewrite `get_income(company, report_date)`** → returns `list` of detail rows:

```sql
SELECT pe.name AS voucher_no, 'Payment Entry' AS voucher_type, pe.posting_date,
	pe.party_name AS party, pe.mode_of_payment, pe.base_paid_amount AS amount,
	GROUP_CONCAT(per.reference_name SEPARATOR ', ') AS linked_invoice
FROM `tabPayment Entry` pe
LEFT JOIN `tabPayment Entry Reference` per
	ON per.parent = pe.name AND per.reference_doctype = 'Sales Invoice'
WHERE pe.docstatus = 1 AND pe.company = %(company)s
	AND pe.posting_date = %(report_date)s AND pe.payment_type = 'Receive'
GROUP BY pe.name
ORDER BY pe.posting_date, pe.name
```

**Rewrite `get_expenses(company, report_date)`** → returns `list` merging:

Query 1 — Pay PEs (same shape, `payment_type = 'Pay'`, `reference_doctype = 'Purchase Invoice'`).
Query 2 — Expense-module direct JEs:

```sql
SELECT je.name AS voucher_no, 'Journal Entry' AS voucher_type, je.posting_date,
	e.payee AS party, je.mode_of_payment, e.amount AS amount, e.name AS linked_invoice
FROM `tabJournal Entry` je
INNER JOIN `tabExpense` e ON e.journal_entry = je.name
WHERE je.docstatus = 1 AND je.company = %(company)s AND je.posting_date = %(report_date)s
```

Merge lists, sort by `(posting_date, voucher_no)`.

**`get_columns()`** — new grid (superset used by all sections):

`section` (Data 60) · `account` (Link Account 220 — Cash & Bank rows only) ·
`voucher_type` (Data, hidden, drives Dynamic Link) · `voucher_no` (Dynamic Link 150) ·
`type` (Data 110, visible "Type") · `party` (Data 170 "Party / Payee") ·
`mode_of_payment` (Data 130) · `linked_invoice` (Data 150 "Linked Invoice / Expense") ·
`posting_date` (Date 90) · `brought_forward` (Currency 120) · `day_movement` (Currency 120) ·
`carried_forward` (Currency 120) · `currency` (Currency, hidden).

**`build_data()`** — Cash & Bank section unchanged. Income section: header →
detail rows → Total Income. Expenses section: header → detail rows → Total Expenses.
Net section unchanged. Replace `_pnl_summary_row`/`_pnl_detail_row` with one detail-row
builder mapping `voucher_no`, `type`, `party`, `mode_of_payment`, `linked_invoice`,
`posting_date`, `day_movement`. **Delete** `_summarize`, `_with_party`,
`_get_je_user_remarks`, `_resolve_party`, and `import re`.

### 2. `apps/nbs_customization/nbs_customization/nbs_customization/page/daily_income_expense/daily_income_expense.py`

`get_data()`: `get_income`/`get_expenses` now return flat lists — drop the unpack of
`_summary`. Totals = sum of row amounts. Response shape unchanged (cards, cash & bank
still work).

### 3. `apps/nbs_customization/nbs_customization/nbs_customization/page/daily_income_expense/daily_income_expense.js`

Refactor `render_pnl_table` to accept a column config and drop the Account column:

- **Income**: Voucher No · Date · Party / Payee · Mode of Payment · Linked Invoice · Amount
- **Expenses**: Voucher No · Type · Date · Party / Payee · Mode of Payment · Linked Invoice / Expense · Amount

Amount formatted with `data.currency` (rows no longer carry `account_currency`). Voucher
cell keeps the `frappe.utils.get_form_link(row.voucher_type, row.voucher_no)` link (works
for Payment Entry and Journal Entry). Total row spans the configured column count.

### 4. `apps/nbs_customization/nbs_customization/tests/test_daily_income_and_expense.py`

- Add `_receive_pe(si)` fixture: build a Receive PE via
  `get_payment_entry("Sales Invoice", si.name)`, set `posting_date = REPORT_DATE`,
  `paid_to = BANK`, `mode_of_payment = "Wire Transfer"`, insert + submit.
- Update `_detail` helper to filter by `voucher_no` (not `account`).
- Update both tests to cash-basis expectations:
  - Bank day = **−50** (+100 income PE, −150 against-PI PE); Cash day = **−100**;
    cash & bank total day = **−150**; carried-forward consistency.
  - Income total = **100**; income row = PE (party = customer, linked_invoice = SI,
    type = Payment Entry, amount 100).
  - Expenses total = **250**; 2 rows: JE (party "Test Payee", linked_invoice = expense
    name, type Journal Entry) + PE (party "_Test Supplier", linked_invoice = PI name,
    type Payment Entry).
  - Net = **−150**.
- `test_dashboard_get_data`: income rows len 1 = the PE; expense rows len 2; income row
  `voucher_no` matches report output.

## Files Touched

- `report/daily_income_and_expense/daily_income_and_expense.py`
- `page/daily_income_expense/daily_income_expense.py`
- `page/daily_income_expense/daily_income_expense.js`
- `nbs_customization/tests/test_daily_income_and_expense.py`

## Verification

1. `ruff` on changed `.py` files; `prettier` on the JS.
2. `bench --site test-site run-tests --app nbs_customization --module nbs_customization.tests.test_daily_income_and_expense`
3. Browser (Administrator / Byaxybagzy@01):
   - Dashboard 12/06/2026 → 3 income PE rows (GIMS 50 blank invoice, ST.JOSEPH 2,341.56 → SI 0004, GIMS 114.90 → SI 0005).
   - Dashboard 05/08/2026 → expenses = 3 PE + 2 JE rows, total 800; income 0; net −800.
   - Script report shows the same rows with Type + Linked Invoice/Expense columns.
