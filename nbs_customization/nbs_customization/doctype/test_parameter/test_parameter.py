# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TestParameter(Document):
	def validate(self):
		if self.result_type == "Calculated" and not self.calculated_from:
			frappe.throw(_("A calculated parameter needs at least one source parameter."))
