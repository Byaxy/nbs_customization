# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Expense(Document):

	def validate(self):
		self._fetch_account_balance()
		self._validate_accompanying()
		self._validate_account_balance()

	def before_submit(self):
		self._validate_account_balance()

	def on_submit(self):
		self._create_journal_entry()

	def on_cancel(self):
		self._cancel_or_delete_lcv()
		self._reverse_journal_entry()

	# ------------------------------------------------------------------ #
	# Validation helpers                                                   #
	# ------------------------------------------------------------------ #

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

			# Validate that the expense category maps to a valuation account
			expense_account = frappe.db.get_value(
				"Expense Category", self.expense_category, "expense_account"
			)
			if expense_account:
				account_type = frappe.db.get_value(
					"Account", expense_account, "account_type"
				)
				# Case-insensitive comparison to handle ERPNext version differences
				if (account_type or "").lower() != "expenses included in valuation":
					frappe.throw(
						f"For accompanying expenses, the Expense Category must map to "
						f"an <b>Expenses Included in Valuation</b> account. "
						f"<b>{self.expense_category}</b> maps to a "
						f"<b>{account_type}</b> account. "
						f"Please use a category linked to your valuation clearing account."
					)
		else:
			self.linked_purchase = None
			self.landed_cost_voucher = None

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
	# Journal Entry                                                        #
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
		je.company = frappe.defaults.get_user_default("Company")
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

    # Get expense account from Expense Category
    expense_account = frappe.db.get_value(
        "Expense Category", expense.expense_category, "expense_account"
    )
    if not expense_account:
        frappe.throw(
            f"No GL account configured for Expense Category: "
            f"{expense.expense_category}."
        )

    company = frappe.defaults.get_user_default("Company")

    lcv = frappe.new_doc("Landed Cost Voucher")
    lcv.company = company
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