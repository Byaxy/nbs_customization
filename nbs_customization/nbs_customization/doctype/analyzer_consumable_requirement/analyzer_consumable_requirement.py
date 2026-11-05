# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AnalyzerConsumableRequirement(Document):
	def validate(self):
		if self.scope == "Selected Applications" and not self.applications:
			frappe.throw(_("Selected Applications scope needs at least one application."))
		if self.scope == "Assay Group" and not self.assay_group:
			frappe.throw(_("Assay Group scope needs an assay group."))
