# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe


def execute():
	if not frappe.db.exists("DocType", "Analyzer Deployment"):
		return
	meta = frappe.get_meta("Analyzer Deployment")
	if meta.has_field("acceptance_attachment"):
		frappe.model.delete_fields({"Analyzer Deployment": ["acceptance_attachment"]}, delete=1)
