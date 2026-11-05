# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe


def execute():
	if not frappe.db.exists("DocType", "Analyzer Test Application"):
		return
	_migrate_test_parameters()
	_migrate_reagent_roles()
	_migrate_test_methods()
	_migrate_consumables()


def _migrate_test_parameters():
	for row in frappe.get_all("Test Parameter", filters={"result_type": ("in", ("", None))}, pluck="name"):
		frappe.db.set_value("Test Parameter", row, "result_type", "Measured")


def _migrate_reagent_roles():
	for row in frappe.get_all(
		"Reagent Specification",
		filters={"item_role": ("in", ("", None))},
		fields=["name", "reagent_role"],
	):
		role = "Test Reagent" if row["reagent_role"] == "Test Reagent" else "Other"
		frappe.db.set_value("Reagent Specification", row["name"], "item_role", role)


def _migrate_test_methods():
	for spec in frappe.get_all("Instrument Specification", fields=["name", "item"]):
		rows = frappe.get_all(
			"Instrument Test Method",
			filters={"parent": spec["name"], "parenttype": "Instrument Specification"},
			fields=[
				"name",
				"test_parameter",
				"required_reagent",
				"default_pack_volume_ml",
				"default_tests_per_pack",
			],
		)
		for row in rows:
			code = f"LEGACY-{row['name']}"
			if frappe.db.exists(
				"Analyzer Test Application",
				{
					"analyzer_item": spec["item"],
					"test_parameter": row["test_parameter"],
					"application_code": code,
				},
			):
				continue
			default_exists = frappe.db.exists(
				"Analyzer Test Application",
				{
					"analyzer_item": spec["item"],
					"test_parameter": row["test_parameter"],
					"is_default": 1,
				},
			)
			frappe.get_doc(
				{
					"doctype": "Analyzer Test Application",
					"analyzer_item": spec["item"],
					"test_parameter": row["test_parameter"],
					"application_code": code,
					"result_type": frappe.db.get_value("Test Parameter", row["test_parameter"], "result_type")
					or "Measured",
					"is_default": 0 if default_exists else 1,
					"reagents": [
						{
							"reagent_item": row["required_reagent"],
							"component_role": "Single",
							"consumption_basis": "Per Test",
							"tests_per_pack_override": row["default_tests_per_pack"] or 0,
							"pack_volume_ml_override": row["default_pack_volume_ml"] or 0,
						}
					],
				}
			).insert(ignore_permissions=True)


def _migrate_consumables():
	for spec in frappe.get_all("Instrument Specification", fields=["name", "item"]):
		rows = frappe.get_all(
			"Instrument Consumable Requirement",
			filters={"parent": spec["name"], "parenttype": "Instrument Specification"},
			fields=["consumable_item", "consumption_frequency", "consumption_qty", "services_per_year"],
		)
		for row in rows:
			if frappe.db.exists(
				"Analyzer Consumable Requirement",
				{
					"analyzer_item": spec["item"],
					"consumable_item": row["consumable_item"],
					"scope": "All Assays",
				},
			):
				continue
			role = frappe.db.get_value("Reagent Specification", {"item": row["consumable_item"]}, "item_role")
			if role not in ("System Solution", "Wash", "Sample Consumable"):
				role = "Other"
			frappe.get_doc(
				{
					"doctype": "Analyzer Consumable Requirement",
					"analyzer_item": spec["item"],
					"consumable_item": row["consumable_item"],
					"consumable_role": role,
					"scope": "All Assays",
					"consumption_basis": row["consumption_frequency"] or "Per Month",
					"qty": row["consumption_qty"] or 0,
					"services_per_year": row["services_per_year"] or 0,
				}
			).insert(ignore_permissions=True)
