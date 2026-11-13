# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

ROLE_MAP = {
	"Single": {"Test Reagent"},
	"R1": {"Test Reagent"},
	"R2": {"Test Reagent"},
	"Diluent": {"Diluent"},
	"Lyse": {"Lyse"},
	"Cleaner": {"Cleaner"},
	"Other": {"Test Reagent", "Diluent", "Lyse", "Cleaner", "Calibrator", "Control"},
}


class AnalyzerProfile(Document):
	def on_update(self):
		frappe.db.set_value(
			"Item",
			self.analyzer_item,
			{"custom_analyzer_profile": self.name, "custom_is_placement_item": 1},
		)

	def on_trash(self):
		if frappe.db.get_value("Item", self.analyzer_item, "custom_analyzer_profile") == self.name:
			frappe.db.set_value("Item", self.analyzer_item, "custom_analyzer_profile", None)

	def validate(self):
		self._validate_duplicates()
		self._validate_reagent_roles()
		self._validate_maintenance_schedule()

	def _validate_duplicates(self):
		seen = set()
		for row in self.reagents:
			key = (row.test_parameter, row.reagent_item, row.component_role)
			if key in seen:
				frappe.throw(
					_("Reagent {0} with role {1} appears twice for test {2}.").format(
						frappe.bold(row.reagent_item),
						frappe.bold(row.component_role),
						frappe.bold(row.test_parameter),
					)
				)
			seen.add(key)

	def _validate_reagent_roles(self):
		for row in self.reagents:
			role = frappe.db.get_value("Reagent Specification", {"item": row.reagent_item}, "item_role")
			if role and role not in ROLE_MAP.get(row.component_role, set()):
				frappe.throw(
					_("Reagent {0} has role {1}, which does not match {2}.").format(
						frappe.bold(row.reagent_item),
						frappe.bold(role),
						frappe.bold(row.component_role),
					)
				)
			if self.system_type == "Closed" and self.manufacturer:
				reagent_manufacturer = frappe.db.get_value(
					"Reagent Specification", {"item": row.reagent_item}, "manufacturer"
				)
				if reagent_manufacturer and reagent_manufacturer != self.manufacturer:
					frappe.throw(
						_("Closed system {0} cannot use reagent {1} from another manufacturer.").format(
							frappe.bold(self.analyzer_item), frappe.bold(row.reagent_item)
						)
					)

	def _validate_maintenance_schedule(self):
		for row in self.maintenance:
			if row.month_no and not 1 <= row.month_no <= 12:
				frappe.throw(_("Maintenance month must be between 1 and 12."))
