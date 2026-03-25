# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Expense(Document):

	def validate(self):
		self._set_company_defaults()
		self._fetch_account_balance()
		self._validate_accompanying()
		self._validate_invoice_link()

	def before_submit(self):
		self._validate_account_balance()

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
			self.cost_center = frappe.db.get_value(
				"Company", self.company, "cost_center"
			)

	def _fetch_account_balance(self):
		"""Fetch current balance of the paying account and store it."""
		if not self.paying_account:
			self.account_balance = 0
			return

		self.account_balance = get_account_balance(
			self.paying_account, self.expense_date
		)


	def _validate_accompanying(self):
		if self.is_accompanying:
			if not self.linked_purchase:
				frappe.throw(
					"Linked Purchase Receipt is required for accompanying expenses."
				)

			# Validate using the category checkbox instead of account_type
			is_accompanying_category = frappe.db.get_value(
				"Expense Category",
				self.expense_category,
				"is_accompanying_expense"
			)
			if not is_accompanying_category:
				frappe.throw(
					f"The Expense Category <b>{self.expense_category}</b> is not marked "
					f"as an Accompanying Expense Category. Please either: <br>"
					f"1. Use a category that has <b>Is Accompanying Expense Category</b> checked, or <br>"
					f"2. Uncheck <b>Is Accompanying Expense</b> on this expense."
				)

			# Validate that the expense account has correct account type
			expense_account = frappe.db.get_value(
				"Expense Category", self.expense_category, "expense_account"
			)
			if expense_account:
				account_type = frappe.db.get_value(
					"Account", expense_account, "account_type"
				)
				if account_type != "Expenses Included In Valuation":
					frappe.throw(
						f"The Expense Account <b>{expense_account}</b> for category "
						f"<b>{self.expense_category}</b> must have Account Type "
						f"<b>'Expenses Included In Valuation'</b> to be used with "
						f"Landed Cost Vouchers. Current type: <b>{account_type or 'None'}</b>."
					)
		else:
			# Validate using the category checkbox instead of account_type
			is_accompanying_category = frappe.db.get_value(
				"Expense Category",
				self.expense_category,
				"is_accompanying_expense"
			)
			if is_accompanying_category:
				frappe.throw(
					f"The Expense Category <b>{self.expense_category}</b> is marked "
					f"as an Accompanying Expense Category. Please either: <br>"
					f"1. Use a category that has <b>Is Accompanying Expense Category</b> Not Checked, or <br>"
					f"2. Check <b>Is Accompanying Expense</b> on this expense."
				)

			# Validate that the expense account has correct account type
			expense_account = frappe.db.get_value(
				"Expense Category", self.expense_category, "expense_account"
			)
			if expense_account:
				account_type = frappe.db.get_value(
					"Account", expense_account, "account_type"
				)
				if account_type == "Expenses Included In Valuation":
					frappe.throw(
						f"The Expense Account <b>{expense_account}</b> for category "
						f"<b>{self.expense_category}</b> must Not have Account Type "
						f"<b>'Expenses Included In Valuation'</b>."
					)
			self.linked_purchase = None
			self.landed_cost_voucher = None

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
			as_dict=True
		)

		if not pi:
			frappe.throw(f"Purchase Invoice {self.purchase_invoice} not found.")

		if pi.docstatus != 1:
			frappe.throw(
				f"Purchase Invoice <b>{self.purchase_invoice}</b> must be submitted "
				f"before it can be paid."
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

	def _validate_account_balance(self):
		"""
		Called before submit. Validates that the paying account
		has sufficient balance to cover this expense.
		"""
		if not self.paying_account:
			frappe.throw("Paying Account is required.")

		# Refresh balance at submit time — not at save time
		current_balance = get_account_balance(
			self.paying_account, self.expense_date
		)

		if current_balance < self.amount:
			frappe.throw(
				f"Insufficient balance in <b>{self.paying_account}</b>. "
				f"Available: <b>{frappe.format_value(current_balance, {'fieldtype': 'Currency'})}</b>, "
				f"Required: <b>{frappe.format_value(self.amount, {'fieldtype': 'Currency'})}</b>, "
				f"Shortfall: <b>{frappe.format_value(self.amount - current_balance, {'fieldtype': 'Currency'})}</b>."
			)

	# ------------------------------------------------------------------ #
	# Flow A — Direct Payment via Journal Entry                           #
	# ------------------------------------------------------------------ #

	def _create_journal_entry(self):
		"""
		On submit: debit the expense category GL account,
		credit the paying account.
		"""
		expense_account = frappe.db.get_value(
			"Expense Category", self.expense_category, "expense_account"
		)
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
		je.user_remark = (
			f"Expense: {self.name} — {self.expense_description} "
			f"| Payee: {self.payee or 'N/A'}"
		)

		# Debit — expense category GL account
		je.append("accounts", {
			"account": expense_account,
			"debit_in_account_currency": self.amount,
			"credit_in_account_currency": 0,
			"cost_center": frappe.db.get_value(
				"Company", je.company, "cost_center"
			),
		})

		# Credit — paying account (cash/bank)
		je.append("accounts", {
			"account": self.paying_account,
			"debit_in_account_currency": 0,
			"credit_in_account_currency": self.amount,
		})

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
		paying_account_currency = frappe.db.get_value(
			"Account", self.paying_account, "account_currency"
		)
		if pi.currency != paying_account_currency:
			frappe.throw(
				f"Currency mismatch: Purchase Invoice is in <b>{pi.currency}</b> "
				f"but Paying Account is in <b>{paying_account_currency}</b>. "
				f"Multi-currency payments are not yet supported in this flow. "
				f"Please use a Payment Entry directly."
			)

		# Use ERPNext's built-in payment entry creation from invoice
		from erpnext.accounts.doctype.payment_entry.payment_entry import (
			get_payment_entry,
		)

		pe = get_payment_entry("Purchase Invoice", self.purchase_invoice)
		pe.posting_date = self.expense_date
		pe.paid_from = self.paying_account
		pe.paid_amount = self.amount
		pe.received_amount = self.amount
		pe.source_exchange_rate = 1
		pe.target_exchange_rate = 1
		pe.reference_no = self.name
		pe.reference_date = self.expense_date
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
				alert=True
			)
		elif lcv.docstatus == 0:
			# Draft — delete it
			frappe.delete_doc(
				"Landed Cost Voucher",
				self.landed_cost_voucher,
				ignore_permissions=True
			)
			frappe.msgprint(
				f"Landed Cost Voucher {self.landed_cost_voucher} has been deleted.",
				indicator="orange",
				alert=True
			)

		self.db_set("landed_cost_voucher", None)


# ------------------------------------------------------------------ #
# Whitelisted helpers (called from JS)                                #
# ------------------------------------------------------------------ #

@frappe.whitelist()
def get_account_balance(account, date=None):
	"""
	Returns the current balance of an account.
	Uses ERPNext's built-in balance utility.
	"""
	from erpnext.accounts.utils import get_balance_on
	return get_balance_on(account=account, date=date)

@frappe.whitelist()
def get_invoice_details(purchase_invoice):
	"""
	Returns key details of a Purchase Invoice for prefilling the Expense form.
	Called from JS when a Purchase Invoice is selected.
	"""
	pi = frappe.db.get_value(
		"Purchase Invoice",
		purchase_invoice,
		["outstanding_amount", "supplier", "company", "bill_no", "docstatus"],
		as_dict=True
	)
	if not pi:
		frappe.throw(f"Purchase Invoice {purchase_invoice} not found.")
	if pi.docstatus != 1:
		frappe.throw(f"Purchase Invoice {purchase_invoice} is not submitted.")
	if pi.outstanding_amount <= 0:
		frappe.throw(
			f"Purchase Invoice {purchase_invoice} has no outstanding amount."
		)
	return pi

@frappe.whitelist()
def make_landed_cost_voucher(expense_name):
	expense = frappe.get_doc("Expense", expense_name)

	if not expense.is_accompanying:
		frappe.throw("This expense is not marked as an accompanying expense.")
	if not expense.linked_purchase:
		frappe.throw("No linked Purchase Receipt found on this expense.")
	if expense.landed_cost_voucher:
		frappe.throw(
			f"A Landed Cost Voucher already exists for this expense: "
			f"{expense.landed_cost_voucher}"
		)
	if expense.docstatus != 1:
		frappe.throw("The expense must be submitted before creating an LCV.")

	pr = frappe.db.get_value(
		"Purchase Receipt",
		expense.linked_purchase,
		["supplier", "grand_total"],
		as_dict=True
	)
	if not pr:
		frappe.throw(f"Purchase Receipt {expense.linked_purchase} not found.")

	expense_account = frappe.db.get_value(
		"Expense Category", expense.expense_category, "expense_account"
	)
	if not expense_account:
		frappe.throw(
			f"No GL account configured for Expense Category: "
			f"{expense.expense_category}."
		)

	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = expense.company
	lcv.distribute_charges_based_on = "Qty"

	lcv.append("purchase_receipts", {
		"receipt_document_type": "Purchase Receipt",
		"receipt_document": expense.linked_purchase,
		"supplier": pr.supplier,
		"grand_total": pr.grand_total,
	})

	lcv.append("taxes", {
		"description": expense.expense_category,
		"expense_account": expense_account,
		"amount": expense.amount,
	})

	lcv.insert(ignore_permissions=True)
	frappe.db.set_value("Expense", expense_name, "landed_cost_voucher", lcv.name)

	return lcv.name