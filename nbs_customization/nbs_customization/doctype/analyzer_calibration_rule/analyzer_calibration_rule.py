# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AnalyzerCalibrationRule(Document):
	def validate(self):
		if self.scope == "Selected Applications" and not self.applications:
			frappe.throw(_("Selected Applications scope needs at least one application."))
		self._validate_duplicate_materials()

	def _validate_duplicate_materials(self):
		seen = set()
		for row in self.materials:
			key = (row.material_item, row.material_role)
			if key in seen:
				frappe.throw(
					_("Material {0} with role {1} appears more than once.").format(
						frappe.bold(row.material_item), frappe.bold(row.material_role)
					)
				)
			seen.add(key)
