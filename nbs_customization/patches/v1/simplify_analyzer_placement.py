# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe

REMOVED_DOCTYPES = (
	"Instrument Specification",
	"Analyzer Type",
	"Analyzer Test Application",
	"Analyzer Application Reagent",
	"Analyzer Consumable Requirement",
	"Analyzer Consumable Application",
	"Analyzer Calibration Rule",
	"Analyzer Calibration Application",
	"Analyzer Calibration Material",
	"Analyzer Maintenance Part",
	"Analyzer Maintenance Schedule",
	"Analyzer Assay Group",
	"Assay Group Test",
	"Assay Group Reagent",
	"Worksheet Volume Line",
	"Worksheet Assay Run",
	"Worksheet Fee Allocation",
	"Contract Fee Allocation",
	"Contract Volume Declaration",
	"Contract Volume Declaration Line",
)


def execute():
	for doctype in REMOVED_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
	_delete_old_custom_fields()
	_ensure_profile_fields()


def _delete_old_custom_fields():
	for name in ("Item-custom_instrument_specification", "Asset-custom_instrument_specification"):
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)


def _ensure_profile_fields():
	for dt, label in (("Item", "Analyzer Profile"), ("Asset", "Analyzer Profile")):
		name = f"{dt}-custom_analyzer_profile"
		if frappe.db.exists("Custom Field", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": dt,
				"fieldname": "custom_analyzer_profile",
				"label": label,
				"fieldtype": "Link",
				"options": "Analyzer Profile",
			}
		).insert(ignore_permissions=True)
