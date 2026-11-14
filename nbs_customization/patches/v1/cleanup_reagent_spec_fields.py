# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe

FIELDS = (
	"pack_volume_ml",
	"gross_tests_per_pack",
	"standard_cost_per_pack",
	"standard_cost_per_unit",
	"calibration_control_pct",
	"dead_volume_pct",
)


def execute():
	if not frappe.db.exists("DocType", "Reagent Specification"):
		return
	meta = frappe.get_meta("Reagent Specification")
	existing = [field for field in FIELDS if meta.has_field(field)]
	if existing:
		frappe.model.delete_fields({"Reagent Specification": existing}, delete=1)
