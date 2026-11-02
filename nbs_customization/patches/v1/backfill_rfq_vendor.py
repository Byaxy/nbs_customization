# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""
Patch: backfill_rfq_vendor
--------------------------
Populates the hidden vendor header field on Request for Quotation with the
first supplier from the Suppliers child table. The standard Supplier list
column reads this field.

Idempotent: only writes records whose vendor differs from the first supplier.
Run position: [post_model_sync].
"""

import frappe


def execute():
	first_suppliers = _get_first_suppliers()
	if not first_suppliers:
		return

	current = dict(
		frappe.get_all(
			"Request for Quotation",
			filters={"name": ["in", list(first_suppliers)]},
			fields=["name", "vendor"],
			as_list=True,
		)
	)

	updates = {
		name: {"vendor": supplier}
		for name, supplier in first_suppliers.items()
		if current.get(name) != supplier
	}

	if updates:
		frappe.db.bulk_update("Request for Quotation", updates, update_modified=False)
		frappe.logger().info(f"[backfill_rfq_vendor] Updated {len(updates)} records")

	frappe.db.commit()


def _get_first_suppliers():
	first_suppliers = {}
	for row in frappe.get_all(
		"Request for Quotation Supplier",
		filters={"parenttype": "Request for Quotation"},
		fields=["parent", "supplier"],
		order_by="parent, idx",
	):
		first_suppliers.setdefault(row.parent, row.supplier)
	return first_suppliers
