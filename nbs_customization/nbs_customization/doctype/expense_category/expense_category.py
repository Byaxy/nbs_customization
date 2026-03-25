# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ExpenseCategory(Document):
	def validate(self):
		self._validate_accompanying_account_type()

	def _validate_accompanying_account_type(self):
		"""
		Validates that if this category is marked as accompanying,
		the linked expense account must be of type 'Expenses Included In Valuation'
		"""
		if not self.is_accompanying_expense:
			return
		
		if not self.expense_account:
			frappe.throw(
				"Expense Account is required for Accompanying Expense Categories."
			)
		
		account_type = frappe.db.get_value(
			"Account", self.expense_account, "account_type"
		)
		
		if account_type != "Expenses Included In Valuation":
			frappe.throw(
				f"For Accompanying Expense Categories, the Expense Account must have "
				f"Account Type = <b>'Expenses Included In Valuation'</b>.<br><br>"
				f"Current Account: <b>{self.expense_account}</b><br>"
				f"Current Type: <b>{account_type or 'None'}</b><br><br>"
				f"Please select an account with the correct type or create a new one "
				f"under <b>Direct Expenses</b>."
			)