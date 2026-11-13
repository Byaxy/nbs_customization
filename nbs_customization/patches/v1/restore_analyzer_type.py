# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe

ANALYZER_TYPES = (
	("Chemistry", "Clinical chemistry analyzer"),
	("Haematology", "Haematology / blood analyzer"),
)


def execute():
	if not frappe.db.exists("DocType", "Analyzer Type"):
		frappe.reload_doc("nbs_customization", "doctype", "analyzer_type", force=True)

	for name, description in ANALYZER_TYPES:
		if frappe.db.exists("Analyzer Type", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Analyzer Type",
				"title": name,
				"description": description,
			}
		).insert(ignore_permissions=True)
