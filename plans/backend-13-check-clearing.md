# B13 — Check (Cheque) Clearing Workflow

**Depends on:** None (standalone; touches the standard Payment Entry and Bank Reconciliation modules)
**Provides:** Clearing accounts for cheques in transit, a single `Check` Mode of Payment with direction-aware posting, two-way clearing (Payment Entry buttons **and** bank-statement reconciliation), cheque-return (bounce) handling that rides native `Payment Entry` cancel, a `Cheques in Transit` report, fixtures, tests, and a scoped commit/push task.

---

## Objective

Capture the timing gap between when a cheque is received/issued and when it actually clears in our bank (or is given to us in cash). Money in transit lives in dedicated clearing accounts; it is moved to the real bank / cash account only when the cheque clears — without ever re-issuing a Payment Entry or receipt to the party. Clearing must be triggerable two ways:

1. **Button-first (normal flow):** user presses **Mark Check Cleared** on the Payment Entry.
2. **Reconcile-time (month-end fallback):** when a bank statement line cannot be matched to any voucher, the user clears the linked cheque from the **Bank Transaction** and the statement line reconciles in the same action.

Works symmetrically for money received from customers (cheque in) and money paid to suppliers (cheque out). Company-currency only in v1.

---

## Design decisions (research-grounded)

- **QuickBooks** uses a two-step model for receivables: payments land in **Undeposited Funds** (a clearing account), then move to the bank via a **Bank Deposit**. Outbound cheques post straight to the bank and are tracked via reconciliation. We generalise both directions with real clearing accounts.
- **ERPNext Bank Reconciliation never creates GL entries.** Matching only stamps a `clearance_date` on the matched voucher (`bank_reconciliation_tool.py:426` `update_clearance_date`; `bank_transaction.py:254` `clear_linked_payment_entry`). Therefore the "reconciliation will move funds" behaviour cannot exist natively.
- **ERPNext reconciliation matches vouchers by their bank-side GL account** (`bank_reconciliation_tool.py:1373`: `paid_from`/`paid_to` == reconciled bank for PEs; `bank_reconciliation_tool.py:1427`: `Journal Entry Account.account` == bank for JEs). Because the cheque Payment Entry posts to the *clearing* account, it is invisible to the real bank's reconciliation tool. **The clearing Journal Entry is the voucher that touches the real bank**, hence it — not the PE — is the reconciliation target. The JE matcher already ranks/auto-matches on `je.cheque_no == transaction.reference_number` (`bank_reconciliation_tool.py:1434`), which we honour by stamping `cheque_no`/`cheque_date` on the clearing JE.
- Native `PaymentEntry.on_cancel` (`payment_entry.py:296`) reverses GL and re-opens invoice allocations (`update_outstanding_amounts`) — the correct primitive for cheque-return.

---

## Data model

### Chart of Accounts (idempotent, created in `setup.py` `after_migrate`)

| Account | Root type | `account_type` | Why |
|---------|-----------|----------------|-----|
| `Current Assets → Cheques in Transit - Inward` | **Asset** | *(blank)* | Money owed to us until customer cheque clears. Blank type keeps it out of the PE Bank/Cash account picker and avoids the mandatory `bank_account` field (`payment_entry.json:421,433`). |
| `Current Liabilities → Cheques in Transit - Outward` | **Liability** | *(blank)* | Money we've promised until supplier cheque is honoured. |

### Custom Fields — `Mode of Payment`

| Field | Type | Purpose |
|-------|------|---------|
| `is_check` | Check | Marks a mode as cheque-based |
| `clearing_account_inward` | Link → Account | Chosen for `payment_type = Receive` |
| `clearing_account_outward` | Link → Account | Chosen for `payment_type = Pay` |
| `default_clearing_destination` | Link → Account | Default Bank/Cash account most cheques clear into (bank OR cash/petty cash) |

### Custom Fields — `Payment Entry`

| Field | Type | Purpose |
|-------|------|---------|
| `is_check` | Check | Read-only; set by validate override |
| `clearing_destination_account` | Link → Account | Auto-filled from MOP, editable; the ledger account funds land in (Bank **or** Cash) |
| `check_cleared` | Check | Set when cleared |
| `check_clearing_date` | Date | Posting date of the clearing JE |
| `check_cleared_source` | Select (`Button` / `Bank Statement`) | Audit trail of which path cleared it |
| `clearing_journal_entry` | Link → Journal Entry | Read-only; traceability of the clearing JE |
| `check_returned` | Check | Set when returned/bounced |
| `check_return_date` | Date | Return date |

### Mode of Payment record

One **`Check`** mode; `default_account` = `clearing_account_inward` (used by the stock JS auto-fill for Receive; the server override + JS fix handle Pay). The two clearing accounts and the default destination are set on it.

---

## Ledger flow

### Receive (customer pays us by cheque)

| Step | Entry |
|------|-------|
| Payment Entry (validate override forces `paid_to`) | Dr `Cheques in Transit - Inward` / Cr `Debtors` (+ allocate invoices) |
| **Mark Check Cleared** (destination Bank or Cash) | Dr `{Bank \| Cash}` / Cr `Cheques in Transit - Inward` |
| **Mark Check Returned** (cleared first) | Cancel clearing JE (Dr `Cheques in Transit - Inward` / Cr `{Bank \| Cash}`) → then cancel PE (Cr `Cheques in Transit - Inward` / Dr `Debtors`, invoice re-opened). Net: Dr `Debtors` / Cr `{Bank \| Cash}` |
| **Mark Check Returned** (never cleared) | Cancel PE only (Cr `Cheques in Transit - Inward` / Dr `Debtors`, invoice re-opened) |

### Pay (we pay supplier by cheque)

| Step | Entry |
|------|-------|
| Payment Entry (validate override forces `paid_from`) | Dr `Creditors` / Cr `Cheques in Transit - Outward` |
| **Mark Check Cleared** (destination Bank or Cash) | Dr `Cheques in Transit - Outward` / Cr `{Bank \| Cash}` |
| **Mark Check Returned** | Cancel clearing JE → then cancel PE. Net: Dr `{Bank \| Cash}` / Cr `Creditors`, supplier payable re-opened |

Invoices settle at Payment Entry time; clearing is a pure balance-sheet transfer, so no receipts/payments are re-issued to anyone.

---

## Shared clearing core — `nbs_customization/controllers/check_clearing.py`

Single source of truth used by **both** entry points so the two-way flow can never double-clear.

```python
import frappe
from frappe import _
from frappe.utils import flt


@frappe.cache()
def get_check_mop(mode_of_payment):
	return frappe.db.get_value(
		"Mode of Payment",
		mode_of_payment,
		[
			"is_check",
			"clearing_account_inward",
			"clearing_account_outward",
			"default_clearing_destination",
		],
		as_dict=1,
	)


def get_clearing_account(pe, mop):
	if pe.payment_type == "Receive":
		return pe.paid_to or mop.clearing_account_inward
	return pe.paid_from or mop.clearing_account_outward


def validate_destination_account(destination_account, company):
	"""Destination must be a Bank or Cash account of the same company in company currency."""
	details = frappe.get_cached_value(
		"Account", destination_account, ["company", "account_type", "account_currency"], as_dict=1
	)
	if not details or details.company != company:
		frappe.throw(
			_("Clearing destination '{0}' is not an account of company '{1}').").format(
				destination_account, company
			)
		)
	if details.account_type not in ("Bank", "Cash"):
		frappe.throw(
			_(
				"Clearing destination '{0}' must be a Bank or Cash account, got type '{1}'."
			).format(destination_account, details.account_type)
		)
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	if details.account_currency != company_currency:
		frappe.throw(
			_(
				"Foreign-currency cheque clearing is not supported yet. Destination '{0}' is in '{1}'."
			).format(destination_account, details.account_currency)
		)
	return details


def create_check_clearing_je(pe, destination_account, clearing_date):
	"""Create and submit the clearing Journal Entry. Idempotency is enforced by callers."""
	validate_destination_account(destination_account, pe.company)
	mop = get_check_mop(pe.mode_of_payment)
	clearing_account = get_clearing_account(pe, mop)

	je = frappe.get_doc(
		doctype="Journal Entry",
		voucher_type="Journal Entry",
		company=pe.company,
		posting_date=clearing_date,
		cheque_no=pe.reference_no,
		cheque_date=pe.reference_date,
		user_remark=_("Cheque clearing against {0}").format(pe.name),
		cost_center=pe.cost_center,
		project=pe.project,
	)
	if pe.payment_type == "Receive":
		je.append(
			"accounts",
			{
				"account": destination_account,
				"debit_in_account_currency": flt(pe.paid_amount),
				"reference_type": "Payment Entry",
				"reference_name": pe.name,
			},
		)
		je.append(
			"accounts",
			{
				"account": clearing_account,
				"credit_in_account_currency": flt(pe.paid_amount),
				"reference_type": "Payment Entry",
				"reference_name": pe.name,
			},
		)
	else:
		je.append(
			"accounts",
			{
				"account": clearing_account,
				"debit_in_account_currency": flt(pe.paid_amount),
				"reference_type": "Payment Entry",
				"reference_name": pe.name,
			},
		)
		je.append(
			"accounts",
			{
				"account": destination_account,
				"credit_in_account_currency": flt(pe.paid_amount),
				"reference_type": "Payment Entry",
				"reference_name": pe.name,
			},
		)
	je.insert(ignore_permissions=True)
	je.submit()
	return je.name


def stamp_check_cleared(pe, je_name, clearing_date, source, destination_account):
	"""Write PE flags after a successful clearing. Guarded via conditional UPDATE."""
	rows = frappe.db.sql(
		"""
		update `tabPayment Entry`
		set is_check = %s, check_cleared = 1, check_clearing_date = %s,
			check_cleared_source = %s, check_returned = 0,
			clearing_destination_account = %s, clearing_journal_entry = %s,
			clearance_date = %s
		where name = %s and docstatus = 1 and ifnull(check_cleared, 0) = 0
		""",
		(
			pe.is_check,
			clearing_date,
			source,
			destination_account,
			je_name,
			clearing_date if _is_bank_account(destination_account) else None,
			pe.name,
		),
	)
	return rows  # 1 if we own the clear, 0 if already raced


def _is_bank_account(account):
	return frappe.get_cached_value("Account", account, "account_type") == "Bank"
```

**Concurrency guard:** `stamp_check_cleared` is a conditional update; only one transaction can flip `check_cleared` 0→1. If it returns 0 rows, the caller cancels the JE it just created and throws — preventing double-clearing regardless of trigger.

---

## Entry point 1 — Payment Entry buttons

### `nbs_customization/controllers/payment_entry.py`

```python
import frappe
from frappe import _

from nbs_customization.controllers.check_clearing import (
	create_check_clearing_je,
	get_check_mop,
	stamp_check_cleared,
	validate_destination_account,
)


def validate_check_payment_entry(pe, method=None):
	"""Force cheque Payment Entries onto the direction-correct clearing account."""
	if pe.payment_type not in ("Receive", "Pay") or not pe.mode_of_payment:
		return
	mop = get_check_mop(pe.mode_of_payment)
	if not mop or not mop.is_check:
		return
	expected = mop.clearing_account_inward if pe.payment_type == "Receive" else mop.clearing_account_outward
	if not expected:
		frappe.throw(
			_("Mode of Payment '{0}' is a cheque mode but has no {1} clearing account set.").format(
				pe.mode_of_payment, "inward" if pe.payment_type == "Receive" else "outward"
			)
		)
	pe.set("is_check", 1)
	bank_side = "paid_to" if pe.payment_type == "Receive" else "paid_from"
	if pe.get(bank_side) != expected:
		pe.set(bank_side, expected)
	if not pe.clearing_destination_account and mop.default_clearing_destination:
		pe.clearing_destination_account = mop.default_clearing_destination


@frappe.whitelist()
def mark_check_cleared(name, destination_account=None, clearing_date=None):
	"""
	Button-driven clearing. Posting date defaults to today; destination defaults
	to the MOP default (Bank or Cash) and is overridable at click time.
	"""
	from frappe.utils import today

	pe = frappe.get_doc("Payment Entry", name)
	if pe.docstatus != 1:
		frappe.throw(_("Only submitted Payment Entries can be marked cleared."))
	mop = get_check_mop(pe.mode_of_payment)
	if not mop or not mop.is_check:
		frappe.throw(_("{0} is not a cheque Payment Entry.").format(pe.name))
	if pe.check_cleared or pe.check_returned:
		frappe.throw(_("{0} is already cleared or returned.").format(pe.name))

	destination_account = destination_account or pe.clearing_destination_account or mop.default_clearing_destination
	clear_date = clearing_date or today()

	je_name = create_check_clearing_je(pe, destination_account, clear_date)
	rows = stamp_check_cleared(pe, je_name, clear_date, "Button", destination_account)
	if rows != 1:
		# lost the race; undo the JE we just created
		frappe.get_doc("Journal Entry", je_name).cancel()
		frappe.throw(_("{0} was already cleared.").format(pe.name))
	return {"journal_entry": je_name, "cleared": True}


@frappe.whitelist()
def mark_check_returned(name):
	"""Cheque bounced. Reverse any clearing, then ride native Payment Entry cancel
	so invoice allocations re-open and future payments are allowed."""
	pe = frappe.get_doc("Payment Entry", name)
	if pe.docstatus != 1:
		frappe.throw(_("Only submitted Payment Entries can be marked returned."))
	if pe.check_returned:
		frappe.throw(_("{0} is already marked returned.").format(pe.name))

	if pe.clearing_journal_entry:
		clearing_je = frappe.get_doc("Journal Entry", pe.clearing_journal_entry)
		if clearing_je.docstatus == 1:
			clearing_je.cancel()

	if pe.check_cleared:
		frappe.db.set_value("Payment Entry", pe.name, "check_cleared", 0)

	pe.cancel()
	frappe.db.set_value(
		"Payment Entry", pe.name, {"check_returned": 1, "check_return_date": frappe.utils.today()}
	)
	return {"returned": True}
```

### JS — extend `nbs_customization/public/js/payment_entry.js`

- On `mode_of_payment` / `payment_type` change: if the mode `is_check`, fetch the direction-correct clearing account from the MOP and set `paid_to`/`paid_from` live (the stock pickers cannot list type-less clearing accounts, so this must be programmatic).
- On `refresh`, when `docstatus === 1 && is_check && !check_cleared && !check_returned`:
  - **Mark Check Cleared** → dialog with `clearing_destination_account` (default MOP default, links filtered to Bank + Cash accounts of the company) and `clearing_date` (default today) → `frappe.call` `mark_check_cleared` → reload / refresh form + message.
  - **Mark Check Returned** → confirmation dialog → `mark_check_returned` → show that the entry is cancelled & invoices re-opened.
- Buttons hidden once `check_cleared`/`check_returned`/`clearing_journal_entry` are set.

---

## Entry point 2 — Bank reconciliation / statement path

### `nbs_customization/controllers/bank_transaction.py`

```python
import frappe
from frappe import _

from nbs_customization.controllers.check_clearing import (
	create_check_clearing_je,
	stamp_check_cleared,
	validate_destination_account,
)


def _bank_gl_account(bank_transaction):
	return frappe.get_cached_value(
		"Bank Account", bank_transaction.bank_account, "account"
	)


@frappe.whitelist()
def get_uncleared_check_candidates(bank_transaction_name):
	"""Candidate uncleared cheque PEs for a statement line, best match first."""
	bt = frappe.get_doc("Bank Transaction", bank_transaction_name)
	payment_type = "Receive" if bt.deposit > 0 else "Pay"
	amount = bt.unallocated_amount or (bt.deposit - bt.withdrawal)
	rows = frappe.db.get_all(
		"Payment Entry",
		filters={
			"docstatus": 1,
			"payment_type": payment_type,
			"is_check": 1,
			"check_cleared": 0,
			"check_returned": 0,
		},
		fields=[
			"name",
			"party",
			"party_type",
			"paid_amount",
			"reference_no",
			"reference_date",
			"posting_date",
			"paid_from",
			"paid_to",
		],
	)
	candidates = []
	for row in rows:
		if abs(row.paid_amount - amount) > 0.01:
			continue
		rank = 0
		if row.reference_no and row.reference_no == bt.reference_number:
			rank += 10
		if row.party == bt.party and row.party_type == bt.party_type:
			rank += 5
		candidates.append({**row, "rank": rank})
	return sorted(candidates, key=lambda r: r["rank"], reverse=True)


@frappe.whitelist()
def clear_check_from_bank_transaction(bank_transaction_name, payment_entry_name):
	"""Reconcile-time clear: creates the clearing JE into the statement's bank account,
	links it to the Bank Transaction so the line reconciles, and stamps the PE."""
	from frappe.utils import flt

	bt = frappe.get_doc("Bank Transaction", bank_transaction_name)
	pe = frappe.get_doc("Payment Entry", payment_entry_name)
	if pe.check_cleared or pe.check_returned:
		frappe.throw(_("{0} is already cleared or returned.").format(pe.name))

	destination_account = _bank_gl_account(bt)
	validate_destination_account(destination_account, bt.company)
	je_name = create_check_clearing_je(pe, destination_account, bt.date)

	rows = stamp_check_cleared(pe, je_name, bt.date, "Bank Statement", destination_account)
	if rows != 1:
		frappe.get_doc("Journal Entry", je_name).cancel()
		frappe.throw(_("{0} was already cleared.").format(pe.name))

	# Link the JE so the statement line reconciles (mirrors create_bulk_bank_entry_and_reconcile)
	bt.append(
		"payment_entries",
		{
			"payment_document": "Journal Entry",
			"payment_entry": je_name,
			"allocated_amount": flt(bt.unallocated_amount or (bt.deposit - bt.withdrawal)),
		},
	)
	bt.save()  # triggers Bank Transaction allocation/clearance-stamping for the JE
	return {"journal_entry": je_name, "bank_transaction": bt.name, "cleared": True}


def clear_check_vouchers_for_period(bank_account, from_date, to_date):
	"""Optional batch: run the same clear+link for every imported/unreconciled transaction
	whose reference number matches an uncleared cheque. Used at month-end."""
	bt_names = frappe.db.get_all(
		"Bank Transaction",
		filters={
			"bank_account": bank_account,
			"date": ["between", [from_date, to_date]],
			"docstatus": 1,
			"unallocated_amount": [">", 0],
		},
		pluck="name",
	)
	cleared = []
	for bt_name in bt_names:
		bt = frappe.get_doc("Bank Transaction", bt_name)
		if not bt.reference_number:
			continue
		candidate = frappe.db.get_value(
			"Payment Entry",
			{"reference_no": bt.reference_number, "docstatus": 1, "is_check": 1, "check_cleared": 0},
			"name",
		)
		if candidate:
			try:
				cleared.append(clear_check_from_bank_transaction(bt_name, candidate))
			except Exception:
				frappe.log_error(frappe.get_traceback(), "cheque clear batch")
	return cleared
```

### JS — `nbs_customization/public/js/bank_transaction.js`

On a submitted `Bank Transaction` with `unallocated_amount > 0`: add **Clear Cheque** button → `frappe.call` `get_uncleared_check_candidates` → dialog listing candidates (PE no, party, amount, cheque no, posting date) → user picks one → `clear_check_from_bank_transaction` → reload. Message shows the created JE + that the statement line is now reconciled.

The button path is **bank-only** (destination = the statement's own bank account). Cash-cleared cheques have no statement line and are handled via the Payment Entry button.

---

## Bank reconciliation integration summary

1. **Normal flow button** creates a JE enriched with `cheque_no`/`cheque_date` from the PE. When the month-end statement is imported, the Bank Reconciliation Tool matches the deposit/withdrawal to this JE (auto-ranked on cheque number, `bank_reconciliation_tool.py:1434`) and stamps its `clearance_date` → Bank Reconciliation Statement ties out.
2. **If the button was missed**, "Clear Cheque" on the Bank Transaction performs the same JE creation and immediately links+reconciles the line in one action.
3. Either way there is exactly one clearing JE per cheque (guarded), and the two paths can never double-post.

---

## Hooks & fixtures wiring (`nbs_customization/hooks.py`)

- `doc_events`:
  - `"Payment Entry": {"validate": "nbs_customization.controllers.payment_entry.validate_check_payment_entry"}`
- `app_include_js`: add `"bank_transaction.js"` (payment JS already included).
- `fixtures` export list: add the `Mode of Payment-*` and `Payment Entry-*` custom fields above (exported to `nbs_customization/fixtures/custom_field.json` via `bench --site ... export-fixtures`).
- Accounts + the `Check` Mode of Payment (with clearing accounts + default destination) created idempotently in `setup.py` `after_migrate`.

---

## Reporting — `Cheques in Transit`

New script report `nbs_customization/nbs_customization/report/cheques_in_transit/` (`.py`/`.js`/`.json`).

- **Open items:** Payment Entries where `is_check=1, docstatus=1, check_cleared=0, check_returned=0` — columns: Payment Entry, DocType series, Party, Reference No, Reference Date, Posting Date, Amount, Payment Type, Clearing Account, **Days Outstanding** (aging). Drives follow-up and month-end review.
- Optional **Cleared items** toggle adds `check_cleared_date`, `check_cleared_source` (Button / Bank Statement) for audit of both paths.

---

## Tests — `nbs_customization/tests/test_check_clearing.py`

Reuse ERPNext test utilities (`create_account`, test company, etc.). Use `frappe.db.rollback()` teardown.

- `test_receive_clear_to_bank` — PE posts to inward clearing; clear JE debits bank, credits clearing; PE flagged.
- `test_receive_clear_to_cash` — same, destination = cash/petty cash account; `clearance_date` left blank.
- `test_pay_clear_to_bank` — PE posts to outward clearing; clear JE debits clearing, credits bank.
- `test_double_clear_guard` — second `mark_check_cleared` on the same PE throws; only one JE exists.
- `test_return_after_clear_reopens_invoice` — clear → return cancels JE + PE; invoice outstanding restored; no duplicate payments.
- `test_return_before_clear` — return cancels PE directly; invoice opens.
- `test_destination_must_be_bank_or_cash` — non-Bank/Cash destination rejected.
- `test_check_pe_forced_to_clearing_account` — validate override pins `paid_to`/`paid_from` regardless of manual entry.
- `test_bank_transaction_clear_links_and_reconciles` — BT clear creates JE, links to `payment_entries`, stamps PE + JE clearance, BT fully allocated.
- `test_bank_transaction_double_clear_guard` — second call across paths throws.

---

## Verification

```bash
# 1. Apply fixtures + accounts/MOP
bench --site test-site migrate

# 2. Rebuild frontend bundles (new/edited JS)
bench build

# 3. Run the app test suite (ruff/pre-commit run first)
ruff check nbs_customization/controllers/check_clearing.py nbs_customization/controllers/payment_entry.py nbs_customization/controllers/bank_transaction.py
bench --site test-site run-tests --app nbs_customization

# 4. Manual sanity (dev site) via agent-browser
#    - Receive PE with Check MOP -> GL on "Cheques in Transit - Inward"
#    - Mark Check Cleared -> JE on bank; button disappears
#    - Create second PE, import a bank statement line, use Clear Cheque -> line reconciles + PE flagged
```

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/controllers/check_clearing.py` | Create — shared clearing core |
| `nbs_customization/controllers/payment_entry.py` | Create — validate override + `mark_check_cleared`/`mark_check_returned` |
| `nbs_customization/controllers/bank_transaction.py` | Create — candidates + `clear_check_from_bank_transaction` (+ optional batch) |
| `nbs_customization/public/js/payment_entry.js` | Modify — direction-aware MOP handler + Clear/Return buttons |
| `nbs_customization/public/js/bank_transaction.js` | Create — Clear Cheque button |
| `nbs_customization/setup.py` | Modify — idempotent clearing accounts + `Check` MOP on `after_migrate` |
| `nbs_customization/hooks.py` | Modify — doc_events, app_include_js, fixture export list |
| `nbs_customization/fixtures/custom_field.json` | Modify — export of new MOP + Payment Entry fields |
| `nbs_customization/nbs_customization/report/cheques_in_transit/` | Create — report (`.py`, `.js`, `.json`) |
| `nbs_customization/tests/test_check_clearing.py` | Create — tests |
| `plans/backend-13-check-clearing.md` | Create — this plan |

---

## Task: commit & push (scoped, leave the rest of the codebase untouched)

The working tree already contains **unrelated in-progress changes** (e.g. `hooks.py` currently carries WIP scheduler_events + placement/reagent fixtures, plus modified `sales_invoice.js`, `purchase_receipt.py`, etc.). This task stages **only** the files/hunks belonging to this plan.

```bash
cd apps/nbs_customization

# 1. Stage new/modified plan files explicitly (NEVER `git add -A` / `git add .`)
git add nbs_customization/controllers/check_clearing.py
git add nbs_customization/controllers/payment_entry.py
git add nbs_customization/controllers/bank_transaction.py
git add nbs_customization/public/js/bank_transaction.js
git add nbs_customization/public/js/payment_entry.js
git add nbs_customization/setup.py
git add nbs_customization/fixtures/custom_field.json
git add nbs_customization/nbs_customization/report/cheques_in_transit/
git add nbs_customization/tests/test_check_clearing.py
git add plans/backend-13-check-clearing.md

# 2. hooks.py is already dirty with unrelated WIP - stage ONLY our hunks
#    (doc_events entry, app_include_js list line, custom-field additions in fixtures export).
#    Select only the hunks that touch check-clearing, NOT scheduler_events / placed-item fixtures.
git add -p nbs_customization/hooks.py

# 3. Review exactly what is staged; confirm nothing unrelated is included
git status
git diff --cached --stat
git diff --cached
```

Commit message (repo style — lowercase, scope prefix, descriptive):

```bash
git commit -m "check clearing: cheque clearing accounts, clear/return actions + bank reconciliation integration"
```

Push to the tracked remote branch (do not force-push, do not rebase/amend unrelated work):

```bash
git push origin main
```

Rules:
- Only the paths/hunks listed above are staged. Every other uncommitted change (README, purchase_receipt.py, fix_layout_sort.py, delivery_note.js, sales_invoice.js, sales_order.js, placement/reagent WIP, etc.) stays in the working tree untouched.
- Run `pre-commit` / `ruff` first (AGENTS.md); resolve failures for *our* files only.
- Verify after push: `git status` still shows the unrelated changes as uncommitted (i.e. not accidentally committed).