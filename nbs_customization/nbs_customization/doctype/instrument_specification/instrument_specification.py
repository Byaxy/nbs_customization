# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InstrumentSpecification(Document):
	def validate(self):
		self._validate_no_duplicate_test_parameters()
		self._validate_reagent_is_test_reagent()
		self._validate_analyzer_type_consistency()

	def _validate_no_duplicate_test_parameters(self):
		seen = set()
		for row in self.get("supported_test_methods") or []:
			if not row.test_parameter:
				continue
			if row.test_parameter in seen:
				frappe.throw(
					frappe._(
						"Test Parameter {0} appears more than once in Supported Test Methods."
					).format(frappe.bold(row.test_parameter))
				)
			seen.add(row.test_parameter)

	def _validate_reagent_is_test_reagent(self):
		for row in self.get("supported_test_methods") or []:
			if not row.required_reagent:
				continue
			rs = frappe.db.get_value(
				"Reagent Specification",
				{"item": row.required_reagent},
				"reagent_role",
			)
			if rs is None:
				frappe.msgprint(
					frappe._(
						"Item {0} has no Reagent Specification. Ensure it is set up before using "
						"this specification in a Worksheet or Contract."
					).format(frappe.bold(row.required_reagent)),
					alert=True,
					indicator="orange",
				)
				continue
			if rs != "Test Reagent":
				frappe.throw(
					frappe._(
						"Item {0} has Reagent Role '{1}', but only items with "
						"Reagent Role 'Test Reagent' are allowed in Supported Test Methods."
					).format(frappe.bold(row.required_reagent), rs)
				)

	def _validate_analyzer_type_consistency(self):
		if not self.analyzer_type:
			return

		for row in self.get("supported_test_methods") or []:
			if row.test_parameter:
				panel = frappe.db.get_value(
					"Test Parameter", row.test_parameter, "test_panel_group"
				)
				if panel:
					panel_at = frappe.db.get_value(
						"Test Panel Group", panel, "analyzer_type"
					)
					if panel_at and panel_at != self.analyzer_type:
						frappe.throw(
							frappe._(
								"Test Parameter {0} belongs to Test Panel Group '{1}' "
								"(Analyzer Type: {2}), which doesn't match '{3}'."
							).format(
								frappe.bold(row.test_parameter),
								panel,
								panel_at,
								self.analyzer_type,
							)
						)

			if row.required_reagent:
				_check_item_analyzer_type(
					row.required_reagent, self.analyzer_type, row.test_parameter
				)

		for row in self.get("required_consumables") or []:
			if row.consumable_item:
				_check_item_analyzer_type(
					row.consumable_item, self.analyzer_type
				)


def _check_item_analyzer_type(item_code, expected_analyzer_type, test_parameter=None):
	rs = frappe.db.get_value(
		"Reagent Specification",
		{"item": item_code},
		"test_panel_group",
	)
	if not rs:
		return
	panel_at = frappe.db.get_value("Test Panel Group", rs, "analyzer_type")
	if panel_at and panel_at != expected_analyzer_type:
		label = frappe.db.get_value("Item", item_code, "item_name") or item_code
		ctx = frappe._(
			"Item {0} belongs to Test Panel Group (Analyzer Type: {1}), "
			"which doesn't match '{2}'."
		).format(
			frappe.bold(label),
			panel_at,
			expected_analyzer_type,
		)
		if test_parameter:
			ctx += " " + frappe._(
				"(Test Parameter: {0})"
			).format(frappe.bold(test_parameter))
		frappe.throw(ctx)
