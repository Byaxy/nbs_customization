# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Drop the legacy placement masters and their worksheet columns.

The rollout is fresh: legacy data is already discarded, so removing the
DocTypes and columns only finishes the schema cleanup. Orphan DocType
removal normally runs during migrate; this patch also covers databases
where the table outlived the DocType record.
"""

import frappe

LEGACY_DOCTYPES = (
	"Instrument Test Method",
	"Instrument Consumable Requirement",
	"Test Panel Group",
	"Worksheet Assay Group",
	"Worksheet Test Price",
	"Contract Assay Group",
	"Contract Test Price",
)

LEGACY_FIELDS = {
	"Instrument Specification": ["supported_test_methods", "required_consumables"],
	"Test Parameter": ["test_panel_group"],
	"Reagent Specification": ["test_panel_group"],
	"Instrument Pricing Worksheet": ["contract_years"],
}


def execute():
	_delete_doctypes()
	_delete_fields()


def _delete_doctypes():
	for doctype in LEGACY_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)


def _delete_fields():
	present = {}
	for doctype, fields in LEGACY_FIELDS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		existing = [field for field in fields if meta.has_field(field)]
		if existing:
			present[doctype] = existing
	if present:
		frappe.model.delete_fields(present, delete=1)
