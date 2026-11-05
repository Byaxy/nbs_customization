# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Copy legacy Test Panel Group rows into Test Panel without removing the old table."""
	if not frappe.db.exists("DocType", "Test Panel"):
		return
	if not frappe.db.exists("DocType", "Test Panel Group"):
		return

	for old in frappe.get_all(
		"Test Panel Group",
		fields=["name", "panel_code", "panel_name", "description"],
	):
		if frappe.db.exists("Test Panel", old["panel_code"]):
			continue

		panel = frappe.get_doc(
			{
				"doctype": "Test Panel",
				"panel_code": old["panel_code"],
				"panel_name": old["panel_name"],
				"description": old.get("description"),
			}
		)
		for idx, param in enumerate(
			frappe.get_all(
				"Test Parameter",
				filters={"test_panel_group": old["name"]},
				fields=["name"],
				order_by="name asc",
			),
			start=1,
		):
			panel.append(
				"parameters",
				{
					"test_parameter": param["name"],
					"sequence": idx,
				},
			)
		panel.insert(ignore_permissions=True)
