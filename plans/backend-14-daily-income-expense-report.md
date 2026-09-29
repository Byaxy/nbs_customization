# B14 — Daily Income and Expense Report

**Depends on:** Existing GL posting from Sales Invoices, Payment Entries, and the custom Expense module (Direct Payment → Journal Entry; Against Purchase Invoice → Payment Entry). **No changes to any existing module — read-only usage of GL data.**
**Provides:** A date-selectable script report showing, for any chosen day: cash & bank position with **balance brought forward / carried forward**, that day's **income** and **expenses** (accrual) with transaction-level detail tables, and **net income** — all computed live from `tabGL Entry`.

---

## Objective

The CEO wants a daily snapshot of income and expenses for any date in the past (day/week/month). For each day they must be able to see:

1. What was earned and spent **that day** — with detail (voucher no, date, account, party/payee, amount), presented as two tables: **Income** and **Expenses**.
2. The **account balances** for that day — petty cash, bank accounts, etc. — expressed as **brought forward** (closing balance of the previous day) and **carried forward** (closing balance of the chosen day), i.e. card-style summary figures.
3. A date picker so they can look at any past day, not just today.

Built-in ERPNext reports are period-oriented (Trial Balance, General Ledger, Account Balance) and none gives a single "day close" view with BF/CF per cash/bank account — hence a small custom report.

---

## Design decisions (research-grounded)

- **`tabGL Entry` is the single source of truth.** Every income and expense event already posts GL entries with a `posting_date`:
  - Income: Sales Invoice (credit Income accounts), Payment Entry `Receive`, Receipt, interest, etc.
  - Expenses: the custom `Expense` doctype → **Direct Payment** creates a Journal Entry (dr expense account / cr paying account); **Against Purchase Invoice** creates a Payment Entry (dr Creditors w/ `party = Supplier` / cr paying account). Also Purchase Invoice payments, payroll, etc.
  - **Verified in the live dev DB** (no code change needed):
    - `ACC-JV-2026-00052` (Expense `NBSEXP-2026/08/0009`, 11 Aug): `Journal Entry` dr `In-Land Transportation - NBS` 100 / cr `Cash - NBS` 100. Note: JE GL rows carry **no party and empty remarks** — the payee lives only in `tabJournal Entry.user_remark` (`Expense: … | Payee: …`).
    - `ACC-PAY-2026-00031` (Expense `NBSEXP-2026/08/0008`, 5 Aug): `Payment Entry` dr `Creditors - NBS` 300 / cr `Cash - NBS` 300, with `party_type=Supplier`, `party=Erba Diagnostics` and remarks on the rows.
- **No snapshot DocType.** Every ERPNext financial report (Trial Balance, GL, P&L) computes live from GL; a frozen "close of day" snapshot would go stale the first time a transaction is posted/cancelled after close and would need nightly generation plus reconciliation forever. Running the report for a past date **is** the snapshot. (Precedent: B13 cheque clearing is also live GL + computed report.)
- **Brought forward / carried forward = opening / closing balance per account.** Exactly the semantics of ERPNext's `get_balance_on(account, date)`: Carried Forward = balance as of the chosen date; Brought Forward = balance as of the previous day. `is_opening` entries (opening JEs) fall into the BF bucket naturally by `posting_date < report_date`. Implemented as one date-bucketed `GROUP BY` — no per-account round trips.
- **Balance convention matches ERPNext:** asset balances = `debit − credit`; income recognized = `credit`; expense incurred = `debit`. Income and expense amounts are presented as positive figures; **Net Income = Income − Expenses**.
- **Dynamic accounts across all sites.** The app runs on 3 production sites with **different charts of accounts** (dev site only has `Cash - NBS`, `ECOBANK LIBERIA`, `Check - NBS`). Account selection is by **type + tree position, never by name**: leaf accounts whose `account_type IN ('Bank','Cash')`, with a fallback for sites that omitted `account_type` — any leaf whose **parent group** has type `Bank`/`Cash`. The summary rows (cards) are derived from this query, so each site automatically shows its own accounts and its own count of cards.
- **Multi-currency safety.** Per-account rows display in the account's own currency (`debit_in_account_currency` / `credit_in_account_currency`). The **Total Cash & Bank** row sums the company-currency columns (`debit`/`credit`) so the total stays meaningful even on a multi-currency site.

---

## Report file layout

```
apps/nbs_customization/nbs_customization/nbs_customization/report/daily_income_and_expense/
├── __init__.py
├── daily_income_and_expense.json
├── daily_income_and_expense.js
└── daily_income_and_expense.py
```

Mirrors the existing `cheques_in_transit` report. Registered by `bench migrate` (Report doctype discovered from folder).

### `daily_income_and_expense.json`

- `report_type`: `Script Report`
- `ref_doctype`: `GL Entry`
- `module`: `NBS Customization`
- `is_standard`: `Yes`
- `roles`: `Accounts User`, `Accounts Manager` (add the CEO role if one exists)

### `daily_income_and_expense.js`

```js
frappe.query_reports["Daily Income and Expense"] = {
	filters: [
		{ fieldname: "company",    label: __("Company"),    fieldtype: "Link", options: "Company", reqd: 1,
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "report_date", label: __("Date"),      fieldtype: "Date",  reqd: 1,
		  default: frappe.datetime.get_today() },
	],
};
```

### `daily_income_and_expense.py`

`execute(filters)` → `(columns, data)`.

Columns (single table; `section` header rows separate the views):

| fieldname | label | fieldtype | notes |
|-----------|-------|-----------|-------|
| `section` | Section | Data | header rows (`CASH & BANK`, `INCOME`, `EXPENSES`, totals) |
| `account` | Account | Link → Account | balance + P&L summary rows, detail rows |
| `party` | Party / Payee | Data | customer / supplier / JE payee |
| `voucher_no` | Voucher No | Dynamic Link (`voucher_type`) | detail rows only |
| `voucher_type` | Voucher Type | Data | hidden; drives the Dynamic Link |
| `posting_date` | Date | Date | detail rows only |
| `brought_forward` | Brought Forward | Currency | balance rows |
| `day_movement` | Day Movement | Currency | signed asset convention for balances; income/expense/net amounts for P&L rows |
| `carried_forward` | Carried Forward | Currency | balance rows |
| `currency` | Currency | Currency | hidden |

Row order:

1. **CASH & BANK — {report_date}** (header)
   - one row per cash/bank account: `brought_forward` | `day_movement` | `carried_forward`
   - **Total Cash & Bank** row (company-currency sum)
2. **INCOME — {report_date}** (header)
   - summary rows (per Income account total) then detail rows (per voucher)
   - **Total Income** row
3. **EXPENSES — {report_date}** (header)
   - summary rows (per expense/payable account total) then detail rows (per voucher)
   - **Total Expenses** row
4. **NET INCOME (LOSS)** — `Total Income − Total Expenses`

---

## SQL sketches

All queries filter `gle.docstatus = 1 AND gle.is_cancelled = 0 AND gle.company = %(company)s`.

### 1. Cash & Bank balances (dynamic account set, single date-bucketed pass)

```sql
SELECT
	gle.account,
	acc.account_currency,
	SUM(CASE WHEN gle.posting_date <  %(report_date)s THEN gle.debit_in_account_currency - gle.credit_in_account_currency ELSE 0 END) AS brought_forward,
	SUM(CASE WHEN gle.posting_date =  %(report_date)s THEN gle.debit_in_account_currency - gle.credit_in_account_currency ELSE 0 END) AS day_movement
FROM `tabGL Entry` gle
INNER JOIN `tabAccount` acc ON acc.name = gle.account
WHERE gle.posting_date <= %(report_date)s
	AND acc.is_group = 0
	AND (
		acc.account_type IN ('Bank', 'Cash')
		OR EXISTS (
			SELECT 1 FROM `tabAccount` pg
			WHERE pg.name = acc.parent_account
			  AND pg.is_group = 1
			  AND pg.account_type IN ('Bank', 'Cash')
		)
	)
GROUP BY gle.account, acc.account_currency;
```

`carried_forward = brought_forward + day_movement`. The **Total** row sums the same account set using the company-currency columns (`debit`, `credit`) so a multi-currency site still gets a meaningful figure.

### 2. Income today (accrual) — credit rows on Income-root accounts

```sql
SELECT gle.voucher_type, gle.voucher_no, gle.posting_date, gle.account,
	gle.party_type, gle.party, gle.credit_in_account_currency AS amount
FROM `tabGL Entry` gle
INNER JOIN `tabAccount` acc ON acc.name = gle.account
WHERE gle.posting_date = %(report_date)s
	AND acc.root_type = 'Income';
```

Summary = aggregate by `account` (Python); detail = the rows above.

### 3. Expenses today — debit rows on Expense-root accounts OR Payable accounts (invoice payments)

```sql
SELECT gle.voucher_type, gle.voucher_no, gle.posting_date, gle.account,
	gle.party_type, gle.party, gle.debit_in_account_currency AS amount
FROM `tabGL Entry` gle
INNER JOIN `tabAccount` acc ON acc.name = gle.account
WHERE gle.posting_date = %(report_date)s
	AND (
		acc.root_type = 'Expense'
		OR acc.account_type = 'Payable'          -- Creditors debited by Payment Entry when paying a PI
	);
```

This captures **both** Expense-module flows (verified above):
- Direct Payment JE → debit lands on an Expense-root account → row 1 of the `OR`
- Against Purchase Invoice PE → debit lands on `Creditors` (Payable) → row 2 of the `OR`

**Party / Payee resolution** (a dedicated helper in the report):

| voucher_type | source |
|---|---|
| `Payment Entry` | `gle.party` (Supplier/Customer) else `gle.remarks` |
| `Journal Entry` | `tabJournal Entry.user_remark` joined on `voucher_no` (payee is only stored there) else `gle.remarks` |

---

## Interaction with existing code

- **`report_customizer.py`** — no config entry needed. The report name is not in `REPORT_CONFIG`, so the `run`/`export_query` wrappers pass it through untouched.
- **Expense module** — untouched; only read its resulting GL rows.
- **Chart of Accounts** — untouched; the report is CoA-agnostic by design (dynamic account selection above).

---

## Testing

New test: `apps/nbs_customization/nbs_customization/tests/test_daily_income_and_expense.py`

Setup on `test-site`:
1. Submit a **Sales Invoice** on a fixed date → income credit.
2. Submit an **Expense** of type **Direct Payment** on the same date → JE (dr expense / cr Cash).
3. Submit an **Expense** of type **Against Purchase Invoice** on the same date → PE (dr Creditors / cr Cash).
4. Call `execute({"company": …, "report_date": …})` and assert:
   - income summary/detail include the invoice credit amount;
   - expense detail includes **both** the expense-account debit (JE) and the `Creditors` debit (PE);
   - `Cash` row: `brought_forward + day_movement == carried_forward` and `carried_forward` reconciles with `get_balance_on("Cash - NBS", date=report_date)`;
   - `Net Income = Total Income − Total Expenses`.

Run:

```bash
bench --site test-site run-tests --app nbs_customization --module nbs_customization.tests.test_daily_income_and_expense
```

Manual browser check on `nbsolutions.localhost`:
- `bench --site nbsolutions.localhost migrate` (registers the Report), then open the report for **2026-08-11** (JE flow) and **2026-08-05** (PE flow); reconcile against the General Ledger report for the same date.

---

## Out of scope (agreed with stakeholder)

- No snapshot DocType, no nightly generation, no daily email.
- No dedicated `Petty Cash` account — the existing `Cash - NBS` account represents petty cash. (Swapping to a real petty cash account later requires no report change — it is picked up automatically.)
- No custom desk page / dashboard — "cards" are delivered as the top summary rows of the report.

---

## Cross-site deployment note

The report is CoA-agnostic: account selection, card rows, and the Total row are all derived per company/site at run time. Each production site automatically reflects its own bank/cash accounts and currencies. No per-site configuration required.
