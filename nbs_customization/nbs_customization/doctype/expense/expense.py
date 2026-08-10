# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Expense(Document):
	def validate(self):
		self._set_company_defaults()
		self._resolve_payment_account()
		self._resolve_paid_to()
		self._set_account_currencies()
		self._validate_category_required()
		self._validate_accompanying()
		self._validate_invoice_link()
		self._validate_bank_reference()

	def on_submit(self):
		if self.payment_type == "Direct Payment":
			self._create_journal_entry()
		else:
			self._create_payment_entry()

	def on_cancel(self):
		self._cancel_or_delete_lcv()
		if self.payment_type == "Direct Payment":
			self._reverse_journal_entry()
		else:
			self._reverse_payment_entry()

	# ------------------------------------------------------------------ #
	# Validation helpers                                                   #
	# ------------------------------------------------------------------ #

	def _set_company_defaults(self):
		if not self.company:
			self.company = frappe.defaults.get_user_default("Company")
		if not self.cost_center:
			self.cost_center = frappe.db.get_value("Company", self.company, "cost_center")

	def _resolve_payment_account(self):
		"""
		Resolve the paying account from the Payment Method, mirroring Payment Entry.
		A manual override of paid_from is respected.
		"""
		if not self.mode_of_payment:
			return

		if not self.paid_from:
			from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
				get_bank_cash_account,
			)

			self.paid_from = get_bank_cash_account(self.mode_of_payment, self.company)["account"]

	def _resolve_paid_to(self):
		"""
		Sets the read-only 'paid to' account based on the payment flow:
		- Against Purchase Invoice → the supplier's payable account.
		- Direct Payment → the expense account of the category (debit side).
		"""
		if self.payment_type == "Against Purchase Invoice" and self.purchase_invoice:
			pi = frappe.db.get_value(
				"Purchase Invoice",
				self.purchase_invoice,
				["supplier", "company"],
				as_dict=True,
			)
			if pi and pi.supplier:
				from erpnext.accounts.party import get_party_account

				self.paid_to = get_party_account("Supplier", pi.supplier, self.company or pi.company)
		else:
			self.paid_to = frappe.db.get_value("Expense Category", self.expense_category, "expense_account")

	def _set_account_currencies(self):
		self.paid_from_account_currency = (
			frappe.db.get_value("Account", self.paid_from, "account_currency") if self.paid_from else None
		)
		self.paid_to_account_currency = (
			frappe.db.get_value("Account", self.paid_to, "account_currency") if self.paid_to else None
		)

	def _validate_category_required(self):
		needs_category = self.payment_type == "Direct Payment" or self.is_accompanying
		if needs_category and not self.expense_category:
			frappe.throw(_("Expense Category is required."))

	def _validate_accompanying(self):
		if not self.is_accompanying:
			# Non-accompanying: clear shipment fields, validate category
			self.expense_scope = None
			self.linked_shipment = None
			self.linked_purchase = None
			self.landed_cost_voucher = None

			is_acc_cat = frappe.db.get_value(
				"Expense Category", self.expense_category, "is_accompanying_expense"
			)
			if is_acc_cat:
				frappe.throw(
					_(
						f"The Expense Category <b>{self.expense_category}</b> is marked "
						f"as an Accompanying Expense Category. Either use a non-accompanying "
						f"category or check <b>Is Accompanying Expense</b> on this expense."
					)
				)
			self._validate_expense_account_type(must_be_valuation=False)
			return

		# --- is_accompanying = True ---
		scope = self.expense_scope or "Single Purchase Receipt"

		# Validate category is accompanying
		is_acc_cat = frappe.db.get_value("Expense Category", self.expense_category, "is_accompanying_expense")
		if not is_acc_cat:
			frappe.throw(
				_(
					f"The Expense Category <b>{self.expense_category}</b> is not marked "
					f"as an Accompanying Expense Category. Please use a category with "
					f"<b>Is Accompanying Expense Category</b> checked."
				)
			)
		self._validate_expense_account_type(must_be_valuation=True)

		if self.payment_type == "Against Purchase Invoice" and self.purchase_invoice:
			self._validate_pi_category_account_match()

		if scope == "Single Purchase Receipt":
			self.linked_shipment = None
			if not self.linked_purchase:
				frappe.throw(_("Linked Purchase Receipt is required for accompanying expenses."))
			# Validate PR belongs to same company
			pr_company = frappe.db.get_value("Purchase Receipt", self.linked_purchase, "company")
			if pr_company and pr_company != self.company:
				frappe.throw(
					_(
						f"Purchase Receipt <b>{self.linked_purchase}</b> belongs to "
						f"company <b>{pr_company}</b>, not <b>{self.company}</b>."
					)
				)

		elif scope == "Inbound Shipment":
			self.linked_purchase = None
			if not self.linked_shipment:
				frappe.throw(
					_("Linked Inbound Shipment is required when Expense Scope is 'Inbound Shipment'.")
				)

			ship = frappe.db.get_value(
				"Inbound Shipment",
				self.linked_shipment,
				["company", "docstatus", "shipment_status"],
				as_dict=True,
			)
			if not ship:
				frappe.throw(_(f"Inbound Shipment <b>{self.linked_shipment}</b> not found."))
			if ship.docstatus != 1:
				frappe.throw(
					_(
						f"Inbound Shipment <b>{self.linked_shipment}</b> must be submitted "
						f"before linking it to an expense."
					)
				)
			if ship.company != self.company:
				frappe.throw(
					_(
						f"Inbound Shipment <b>{self.linked_shipment}</b> belongs to "
						f"company <b>{ship.company}</b>, not <b>{self.company}</b>."
					)
				)

	def _validate_pi_category_account_match(self):
		message = get_pi_category_account_mismatch(self)
		if message:
			frappe.throw(message)

	def _validate_expense_account_type(self, must_be_valuation: bool):
		expense_account = frappe.db.get_value("Expense Category", self.expense_category, "expense_account")
		if not expense_account:
			return
		account_type = frappe.db.get_value("Account", expense_account, "account_type")
		if must_be_valuation and account_type != "Expenses Included In Valuation":
			frappe.throw(
				_(
					f"The Expense Account <b>{expense_account}</b> for category "
					f"<b>{self.expense_category}</b> must have Account Type "
					f"<b>'Expenses Included In Valuation'</b> for accompanying expenses. "
					f"Current type: <b>{account_type or 'None'}</b>."
				)
			)
		if not must_be_valuation and account_type == "Expenses Included In Valuation":
			frappe.throw(
				_(
					f"The Expense Account <b>{expense_account}</b> for category "
					f"<b>{self.expense_category}</b> must NOT have Account Type "
					f"<b>'Expenses Included In Valuation'</b> for non-accompanying expenses."
				)
			)

	def _validate_invoice_link(self):
		"""Validates the linked Purchase Invoice for Flow B."""
		if self.payment_type != "Against Purchase Invoice":
			self.purchase_invoice = None
			return
		if not self.purchase_invoice:
			frappe.throw("Purchase Invoice is required for Against Purchase Invoice payment type.")

		pi = frappe.db.get_value(
			"Purchase Invoice",
			self.purchase_invoice,
			["docstatus", "outstanding_amount", "company", "supplier"],
			as_dict=True,
		)

		if not pi:
			frappe.throw(f"Purchase Invoice {self.purchase_invoice} not found.")

		if pi.docstatus != 1:
			frappe.throw(
				f"Purchase Invoice <b>{self.purchase_invoice}</b> must be submitted before it can be paid."
			)

		if pi.outstanding_amount <= 0:
			frappe.throw(
				f"Purchase Invoice <b>{self.purchase_invoice}</b> has no outstanding "
				f"amount. It may already be fully paid."
			)

		if pi.company != self.company:
			frappe.throw(
				f"Purchase Invoice <b>{self.purchase_invoice}</b> belongs to company "
				f"<b>{pi.company}</b> but this expense is for <b>{self.company}</b>."
			)

		# Auto-set amount from invoice outstanding if not set
		if not self.amount:
			self.amount = pi.outstanding_amount

	def _validate_bank_reference(self):
		"""
		Mirror Payment Entry's validate_transaction_reference: when the paying
		account is a Bank account (bank transfer or cheque), the Cheque/Reference
		No and Cheque/Reference Date are mandatory.
		"""
		if not self.paid_from:
			return

		account_type = frappe.get_cached_value("Account", self.paid_from, "account_type")
		if account_type != "Bank":
			return

		if not self.reference_no or not self.reference_date:
			frappe.throw(_("Reference No and Reference Date is mandatory for Bank transaction"))

	# ------------------------------------------------------------------ #
	# Flow A — Direct Payment via Journal Entry                           #
	# ------------------------------------------------------------------ #

	def _create_journal_entry(self):
		"""
		On submit: debit the expense category GL account,
		credit the paying account.
		"""
		expense_account = frappe.db.get_value("Expense Category", self.expense_category, "expense_account")
		if not expense_account:
			frappe.throw(
				f"No GL account configured for Expense Category: "
				f"<b>{self.expense_category}</b>. "
				f"Please set the Expense Account on the category."
			)

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.expense_date
		je.mode_of_payment = self.mode_of_payment
		je.cheque_no = self.reference_no
		je.cheque_date = self.reference_date
		je.user_remark = f"Expense: {self.name} — {self.expense_description} | Payee: {self.payee or 'N/A'}"

		# Debit — expense category GL account
		je.append(
			"accounts",
			{
				"account": expense_account,
				"debit_in_account_currency": self.amount,
				"credit_in_account_currency": 0,
				"cost_center": frappe.db.get_value("Company", je.company, "cost_center"),
			},
		)

		# Credit — paying account (cash/bank)
		je.append(
			"accounts",
			{
				"account": self.paid_from,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": self.amount,
			},
		)

		je.insert(ignore_permissions=True)
		je.submit()

		# Store JE reference on this expense
		self.db_set("journal_entry", je.name)

	def _reverse_journal_entry(self):
		"""
		On cancel: cancel the linked Journal Entry.
		"""
		if not self.get("journal_entry"):
			return

		je = frappe.get_doc("Journal Entry", self.journal_entry)
		if je.docstatus == 1:
			je.cancel()

		self.db_set("journal_entry", None)

	# ------------------------------------------------------------------ #
	# Flow B — Against Purchase Invoice via Payment Entry                 #
	# ------------------------------------------------------------------ #

	def _create_payment_entry(self):
		"""
		Creates a Payment Entry to pay the linked Purchase Invoice.
		This is ERPNext-native and correctly reconciles AP.
		"""
		pi = frappe.get_doc("Purchase Invoice", self.purchase_invoice)

		# Guard: warn if currencies differ
		paid_from_currency = frappe.db.get_value("Account", self.paid_from, "account_currency")
		if pi.currency != paid_from_currency:
			frappe.throw(
				f"Currency mismatch: Purchase Invoice is in <b>{pi.currency}</b> "
				f"but Account Paid From is in <b>{paid_from_currency}</b>. "
				f"Multi-currency payments are not yet supported in this flow. "
				f"Please use a Payment Entry directly."
			)

		# Use ERPNext's built-in payment entry creation from invoice
		from erpnext.accounts.doctype.payment_entry.payment_entry import (
			get_payment_entry,
		)

		pe = get_payment_entry("Purchase Invoice", self.purchase_invoice)
		pe.posting_date = self.expense_date
		pe.paid_from = self.paid_from
		pe.paid_amount = self.amount
		pe.received_amount = self.amount
		pe.source_exchange_rate = 1
		pe.target_exchange_rate = 1
		pe.mode_of_payment = self.mode_of_payment
		pe.reference_no = self.reference_no
		pe.reference_date = self.reference_date or self.expense_date
		pe.remarks = (
			f"Payment via Expense {self.name} — {self.expense_description} "
			f"| Payee: {self.payee or pi.supplier}"
		)

		# Set the allocated amount on the reference row
		for ref in pe.references:
			if ref.reference_name == self.purchase_invoice:
				ref.allocated_amount = min(self.amount, ref.outstanding_amount)

		pe.insert(ignore_permissions=True)
		pe.submit()
		self.db_set("payment_entry", pe.name)

	def _reverse_payment_entry(self):
		if not self.get("payment_entry"):
			return
		pe = frappe.get_doc("Payment Entry", self.payment_entry)
		if pe.docstatus == 1:
			pe.cancel()
		self.db_set("payment_entry", None)

	# ------------------------------------------------------------------ #
	# LCV handling                                                        #
	# ------------------------------------------------------------------ #

	def _cancel_or_delete_lcv(self):
		"""
		On cancel: if an LCV was created for this accompanying expense,
		cancel it if submitted or delete it if still draft.
		"""
		if not self.get("landed_cost_voucher"):
			return

		if not frappe.db.exists("Landed Cost Voucher", self.landed_cost_voucher):
			self.db_set("landed_cost_voucher", None)
			return

		lcv = frappe.get_doc("Landed Cost Voucher", self.landed_cost_voucher)

		if lcv.docstatus == 1:
			# Submitted — cancel it
			lcv.cancel()
			frappe.msgprint(
				f"Landed Cost Voucher {self.landed_cost_voucher} has been cancelled.",
				indicator="orange",
				alert=True,
			)
		elif lcv.docstatus == 0:
			# Draft — delete it
			frappe.delete_doc("Landed Cost Voucher", self.landed_cost_voucher, ignore_permissions=True)
			frappe.msgprint(
				f"Landed Cost Voucher {self.landed_cost_voucher} has been deleted.",
				indicator="orange",
				alert=True,
			)

		self.db_set("landed_cost_voucher", None)


# ------------------------------------------------------------------ #
# Whitelisted helpers (called from JS)                                #
# ------------------------------------------------------------------ #


@frappe.whitelist()
def get_invoice_details(purchase_invoice):
	"""
	Returns key details of a Purchase Invoice for prefilling the Expense form.
	Called from JS when a Purchase Invoice is selected.
	"""
	pi = frappe.db.get_value(
		"Purchase Invoice",
		purchase_invoice,
		["outstanding_amount", "supplier", "supplier_name", "company", "bill_no", "docstatus"],
		as_dict=True,
	)
	if not pi:
		frappe.throw(f"Purchase Invoice {purchase_invoice} not found.")
	if pi.docstatus != 1:
		frappe.throw(f"Purchase Invoice {purchase_invoice} is not submitted.")
	if pi.outstanding_amount <= 0:
		frappe.throw(f"Purchase Invoice {purchase_invoice} has no outstanding amount.")
	return pi


@frappe.whitelist()
def get_purchase_invoices_search(doctype, txt, searchfield, start, page_len, filters):
	"""
	Custom Link-search for the Purchase Invoice field on the Expense form.
	Shows invoice no, supplier, grand total, outstanding amount and posting date
	in the dropdown, and excludes already-paid/cancelled invoices.
	"""
	company = (filters or {}).get("company")

	return frappe.db.sql(
		"""
		SELECT
			pi.name,
			pi.supplier_name,
			pi.grand_total,
			pi.outstanding_amount,
			pi.posting_date
		FROM `tabPurchase Invoice` pi
		WHERE pi.docstatus = 1
			AND pi.status NOT IN ('Paid', 'Cancelled')
			AND (%(company)s IS NULL OR pi.company = %(company)s)
			AND (
				pi.name LIKE %(txt)s
				OR IFNULL(pi.supplier_name, '') LIKE %(txt)s
				OR IFNULL(pi.bill_no, '') LIKE %(txt)s
			)
		ORDER BY pi.posting_date DESC, pi.name DESC
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"company": company,
			"txt": f"%{txt}%",
			"page_len": page_len,
			"start": start,
		},
	)


@frappe.whitelist()
def get_payment_method_account(mode_of_payment, company):
	"""
	Resolves the default Cash/Bank account for a Mode of Payment and Company,
	plus that account's currency. Mirrors Payment Entry's paid_from auto-fill.
	"""
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
		get_bank_cash_account,
	)

	account = get_bank_cash_account(mode_of_payment, company)["account"]
	account_currency = frappe.db.get_value("Account", account, "account_currency")
	return {"account": account, "account_currency": account_currency}


@frappe.whitelist()
def get_supplier_payable_details(supplier, company):
	"""
	Returns the payable account and its currency for a Supplier in a Company.
	Used to prefill 'Account Paid To' on the Against Purchase Invoice flow.
	"""
	from erpnext.accounts.party import get_party_account

	payable_account = get_party_account("Supplier", supplier, company)
	account_currency = frappe.db.get_value("Account", payable_account, "account_currency")
	return {"paid_to": payable_account, "account_currency": account_currency}


@frappe.whitelist()
def check_shipment_fully_received(shipment_name):
	"""
	Checks whether all items in the shipment's package_items have been
	fully received in submitted PRs tagged to this shipment via the
	inbound_shipment field on Purchase Receipt.
	"""
	shipment_items = frappe.db.sql(
		"""
		SELECT
			purchase_order,
			item_code,
			SUM(qty) AS expected_qty
		FROM `tabInbound Shipment Package Item`
		WHERE parent       = %(shipment)s
		AND purchase_order IS NOT NULL AND purchase_order != ''
		AND item_code      IS NOT NULL AND item_code      != ''
		GROUP BY purchase_order, item_code
		""",
		{"shipment": shipment_name},
		as_dict=True,
	)

	if not shipment_items:
		return {
			"ready": False,
			"message": "No package items with Purchase Order references found on this shipment.",
			"unreceived_items": [],
		}

	unreceived = []

	for row in shipment_items:
		result = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(pri.qty), 0)
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pr.custom_inbound_shipment = %(shipment)s
			AND pri.purchase_order  = %(po)s
			AND pri.item_code       = %(item_code)s
			AND pr.docstatus        = 1
			""",
			{
				"shipment": shipment_name,
				"po": row.purchase_order,
				"item_code": row.item_code,
			},
		)

		received_qty = flt(result[0][0]) if result else 0.0
		expected = flt(row.expected_qty)

		if received_qty < expected:
			unreceived.append(
				{
					"purchase_order": row.purchase_order,
					"item_code": row.item_code,
					"expected_qty": expected,
					"received_qty": received_qty,
					"pending_qty": flt(expected - received_qty, 3),
				}
			)

	if unreceived:
		lines = "".join(
			[
				f"<li><b>{r['item_code']}</b> from <b>{r['purchase_order']}</b> — "
				f"expected {r['expected_qty']}, received {r['received_qty']}, "
				f"pending {r['pending_qty']}</li>"
				for r in unreceived
			]
		)
		message = (
			f"The following items have not been fully received for this shipment:<br>"
			f"<ul>{lines}</ul>"
			f"All shipment items must be received before creating a Landed Cost Voucher."
		)
	else:
		message = None

	return {
		"ready": len(unreceived) == 0,
		"unreceived_items": unreceived,
		"message": message,
	}


def get_pi_category_account_mismatch(expense):
	"""
	Returns a user-facing error message if the expense's category account does not match
	the account its linked Purchase Invoice booked its cost to, else None.

	The LCV credits only the category's expense account, so a mismatch would strand the
	invoice's debit on the P&L while booking a spurious credit on the category account.
	"""
	if not (expense.payment_type == "Against Purchase Invoice" and expense.purchase_invoice):
		return None

	category_account = frappe.db.get_value("Expense Category", expense.expense_category, "expense_account")
	if not category_account:
		return None

	pi_accounts = list(
		{
			row["expense_account"]
			for row in frappe.db.get_all(
				"Purchase Invoice Item",
				filters={"parent": expense.purchase_invoice, "expense_account": ["is", "set"]},
				fields=["expense_account"],
			)
		}
	)
	if not pi_accounts:
		return None

	if len(pi_accounts) > 1:
		return _(
			f"Purchase Invoice <b>{expense.purchase_invoice}</b> booked its cost to multiple "
			f"expense accounts (<b>{', '.join(sorted(pi_accounts))}</b>). For accompanying expenses "
			f"paid against an invoice, the invoice must book its cost to a single expense account "
			f"matching the category <b>{expense.expense_category}</b> (<b>{category_account}</b>) so "
			f"the Landed Cost Voucher clears it in full."
		)

	if pi_accounts[0] != category_account:
		return _(
			f"Purchase Invoice <b>{expense.purchase_invoice}</b> booked its cost to "
			f"<b>{pi_accounts[0]}</b>, but Expense Category <b>{expense.expense_category}</b> points "
			f"to <b>{category_account}</b>. For accompanying expenses paid against an invoice, the "
			f"category must point to the same account the invoice booked so the Landed Cost Voucher "
			f"clears it in full. Change the category or use Direct Payment."
		)

	return None


@frappe.whitelist()
def make_landed_cost_voucher(expense_name):
	"""
	Creates a Landed Cost Voucher for an accompanying expense.
	Supports both scope types:
		- 'Single Purchase Receipt' → one PR on the LCV
		- 'Inbound Shipment'        → all PRs from the shipment on the LCV
	"""
	expense = frappe.get_doc("Expense", expense_name)

	# --- Guards ---
	if not expense.is_accompanying:
		frappe.throw(_("This expense is not marked as an accompanying expense."))
	if expense.docstatus != 1:
		frappe.throw(_("The expense must be submitted before creating an LCV."))
	if expense.landed_cost_voucher:
		frappe.throw(
			_(f"A Landed Cost Voucher already exists for this expense: <b>{expense.landed_cost_voucher}</b>")
		)

	mismatch = get_pi_category_account_mismatch(expense)
	if mismatch:
		frappe.throw(mismatch)

	scope = expense.expense_scope or "Single Purchase Receipt"

	# --- Shipment fully received guard (Inbound Shipment scope only) ---
	if scope == "Inbound Shipment" and expense.linked_shipment:
		receipt_check = check_shipment_fully_received(expense.linked_shipment)
		if not receipt_check["ready"]:
			frappe.throw(_(receipt_check["message"]))

	expense_account = frappe.db.get_value("Expense Category", expense.expense_category, "expense_account")
	if not expense_account:
		frappe.throw(_(f"No GL account configured for Expense Category: <b>{expense.expense_category}</b>."))

	# --- Collect purchase receipts for LCV ---
	if scope == "Single Purchase Receipt":
		if not expense.linked_purchase:
			frappe.throw(_("No linked Purchase Receipt found on this expense."))
		pr_doc = frappe.db.get_value(
			"Purchase Receipt",
			expense.linked_purchase,
			["supplier", "grand_total"],
			as_dict=True,
		)
		if not pr_doc:
			frappe.throw(_(f"Purchase Receipt {expense.linked_purchase} not found."))
		pr_rows = [
			{
				"receipt_document": expense.linked_purchase,
				"supplier": pr_doc.supplier,
				"grand_total": pr_doc.grand_total,
			}
		]

	elif scope == "Inbound Shipment":
		if not expense.linked_shipment:
			frappe.throw(_("No Inbound Shipment linked to this expense."))
		pr_rows = frappe.db.get_all(
			"Inbound Shipment Purchase Receipt",
			filters={"parent": expense.linked_shipment},
			fields=["receipt_document", "supplier", "grand_total"],
			order_by="idx asc",
		)
		if not pr_rows:
			frappe.throw(
				_(f"Inbound Shipment <b>{expense.linked_shipment}</b> has no linked Purchase Receipts.")
			)
	else:
		frappe.throw(_(f"Unknown expense scope: {scope}"))

	# --- Build LCV ---
	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = expense.company

	if scope == "Inbound Shipment":
		# Lock to manual so ERPNext never auto-overrides our weight distribution
		lcv.distribute_charges_based_on = "Distribute Manually"

	for row in pr_rows:
		lcv.append(
			"purchase_receipts",
			{
				"receipt_document_type": "Purchase Receipt",
				"receipt_document": row["receipt_document"],
				"supplier": row["supplier"],
				"grand_total": row["grand_total"],
			},
		)

	lcv.append(
		"taxes",
		{
			"description": expense.expense_category,
			"expense_account": expense_account,
			"amount": expense.amount,
		},
	)

	if scope == "Inbound Shipment" and expense.linked_shipment:
		lcv.custom_linked_shipment = expense.linked_shipment

	lcv.insert(ignore_permissions=True)
	frappe.db.set_value("Expense", expense_name, "landed_cost_voucher", lcv.name)

	return lcv.name
