# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AnalyzerMaintenancePart(Document):
	def validate(self):
		for row in self.schedule:
			if row.month_no < 1 or row.month_no > 12:
				frappe.throw(_("Schedule month must be between 1 and 12."))
