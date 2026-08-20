# Backend-17 — Commission Payouts in Daily Income/Expense

## Context / Problem

The Daily Income and Expense report (B14/B16) and dashboard page (B15/B16) report
expenses as actual money out via:

1. Payment Entries against Purchase Invoices (`payment_type = 'Pay'`), and
2. Direct Journal Entries from the Expense module (`tabExpense.journal_entry`).

The Commissions module pays sales people through **Commission Payout** documents that
post their own Journal Entry (`tabCommission Payout.journal_entry`). Because that JE is
not linked to `tabExpense`, commission payments never appear in the expense tables —
even though Cash & Bank balances already include them.

### Verified example — 2026-08-05
- Commission Payout `NBSCOMM-PAY-2026/08/0002`
  - sales_person = **Roger Parker**, amount_to_pay = **90.09**
  - mode_of_payment = **Cash**, paid_from = **Cash - NBS**
  - expense_category = **Sales Commissions**
  - commission = **NBSCOMM-2026/04/0003**
  - journal_entry = **ACC-JV-2026-00048** (posting_date = payout_date = 2026-08-05)
- The report currently shows Total Expenses = 800 on 05-08; with the payout it should be **890.09**.

## Decisions (confirmed with user)

1. Source of truth = **Commission Payout** doc (not the JE): it carries sales person,
   mode of payment, amount, date, expense category and commission reference. Its
   posting date equals the JE posting date by construction. No double-counting risk
   (PEs and Expense-module JEs are separate sources).
2. Type label for commission rows = **"Commission Payout"**.
3. Expenses-table linked column header renamed to **"Linked Ref"** (covers Purchase
   Invoice / Expense No / Sales Commission).

## Implementation

### 1. `apps/nbs_customization/nbs_customization/nbs_customization/report/daily_income_and_expense/daily_income_and_expense.py`

Add a third query to `get_expenses` and merge into the existing `rows + je_rows` list
(same `(posting_date, voucher_no)` sort):

```sql
SELECT cp.name AS voucher_no, 'Commission Payout' AS voucher_type, cp.payout_date AS posting_date,
	cp.sales_person AS party, cp.mode_of_payment, cp.amount_to_pay AS amount, cp.commission AS linked_invoice
FROM `tabCommission Payout` cp
WHERE cp.docstatus = 1 AND cp.company = %(company)s AND cp.payout_date = %(report_date)s
```

No column changes: `_pnl_detail_row` already maps `type` = voucher_type, party,
mode_of_payment, linked_invoice, day_movement. Voucher stays a Dynamic Link →
Commission Payout.

### 2. `apps/nbs_customization/nbs_customization/nbs_customization/page/daily_income_expense/daily_income_expense.py`

No change — commission rows flow through `expense_detail`; `type` is derived from
`voucher_type` for all rows.

### 3. `apps/nbs_customization/nbs_customization/nbs_customization/page/daily_income_expense/daily_income_expense.js`

Rename the expenses table header from `__("Linked Invoice / Expense")` to
`__("Linked Ref")`. No logic change.

### 4. `apps/nbs_customization/nbs_customization/tests/test_daily_income_and_expense.py`

Add fixture `_commission_payout(si, amount=90.09)`:

- Create Sales Person "Test Sales Person" (`sales_person_name`, `enabled`).
- Build Sales Commission:
  - company = `_Test Company`, customer = `si.customer`, commission_date = REPORT_DATE
  - one `commission_sales` row (`sale = si.name`, `commission_rate = 100`)
  - one `commission_recipients` row (`sales_person` = Test Sales Person,
    `allocated_amount` = total payable = 100, since SI grand total = 100)
  - insert + submit
- Build Commission Payout:
  - commission = sc.name, commission_recipient = sc.commission_recipients[0].name
  - payout_date = REPORT_DATE, amount_to_pay = amount
  - expense_category = Test Expense Category, mode_of_payment = "Wire Transfer"
  - paid_from = BANK, company = `_Test Company`
  - insert + submit

Update both tests (`test_report_balances_and_pnl`, `test_dashboard_get_data`):

- Bank day movement: −50 − 90.09 = **−140.09**; Cash day: **−100**;
  cash & bank total day: **−240.09** (carried-forward consistency kept).
- Expenses total: **340.09**; expense rows: **3**.
- Commission Payout row: `voucher_no` = payout name, `type` = "Commission Payout",
  `party` = "Test Sales Person", `mode_of_payment` = "Wire Transfer",
  `linked_invoice` = commission name, `amount`/`day_movement` = 90.09.
- Net = 100 − 340.09 = **−240.09**.
- Cleanup order: cancel payout → cancel commission → cancel existing docs.

## Files Touched

- `report/daily_income_and_expense/daily_income_and_expense.py`
- `page/daily_income_expense/daily_income_expense.js`
- `nbs_customization/tests/test_daily_income_and_expense.py`

## Verification

1. `ruff` on changed `.py` files; `prettier` on the JS.
2. `bench --site test-site run-tests --app nbs_customization --module nbs_customization.tests.test_daily_income_and_expense`
3. Browser (Administrator / Byaxybagzy@01):
   - Dashboard 05-08-2026 → expenses total **890.09**, rows = 2 JE + 3 PE + 1
     Commission Payout (NBSCOMM-PAY-2026/08/0002, Roger Parker, Cash,
     linked NBSCOMM-2026/04/0003).
   - Script report grid shows the same rows with Type = "Commission Payout".
   - Screenshot for the record.