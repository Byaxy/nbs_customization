# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AnalyzerTestApplication(Document):
	def validate(self):
		self._validate_default_uniqueness()
		self._validate_reagent_roles()

	def _validate_default_uniqueness(self):
		if not self.is_default:
			return
		key = {
			"analyzer_item": self.analyzer_item,
			"test_parameter": self.test_parameter,
			"sample_type": self.sample_type or "",
			"is_default": 1,
			"name": ("!=", self.name or ""),
		}
		if self.method:
			key["method"] = self.method
		existing = frappe.db.get_value("Analyzer Test Application", key, "name")
		if existing:
			frappe.throw(
				_(
					"Default application already exists for this analyzer, parameter, and sample type: {0}"
				).format(frappe.bold(existing))
			)

	def _validate_reagent_roles(self):
		for row in self.reagents:
			role = frappe.db.get_value("Reagent Specification", {"item": row.reagent_item}, "item_role")
			if not role:
				continue
			allowed = {
				"R1": {"Test Reagent"},
				"R2": {"Test Reagent"},
				"Single": {"Test Reagent"},
				"Diluent": {"Diluent"},
				"Lyse": {"Lyse"},
				"Cleaner": {"Cleaner"},
				"Other": {"Test Reagent", "Diluent", "Lyse", "Cleaner", "Other"},
			}
			if role not in allowed.get(row.component_role, set()):
				frappe.throw(
					_("Reagent {0} has role {1}, which does not match component role {2}.").format(
						frappe.bold(row.reagent_item), frappe.bold(role), frappe.bold(row.component_role)
					)
				)
