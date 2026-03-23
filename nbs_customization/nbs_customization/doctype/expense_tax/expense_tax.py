# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ExpenseTax(Document):
	def validate(self):
		if self.tax_percentage < 0:
			frappe.throw("Tax Percentage cannot be negative.")
