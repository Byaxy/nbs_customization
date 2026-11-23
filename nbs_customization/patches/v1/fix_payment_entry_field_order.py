# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""
Patch: fix_payment_entry_field_order
------------------------------------
ERPNext 16.60 (commit d498958cc7) removed the `transaction_references` Section
Break and moved `reference_no` / `reference_date` / `clearance_date` into the
`payment_accounts_section`.

Sites that customised the Payment Entry form keep a stale site-level
Property Setter `Payment Entry-main-field_order` that still references the old
layout. `Meta.sort_fields` drops the now-missing names but keeps the surviving
fields at their stale positions, so `reference_no`, `reference_date`,
`check_bank` and the cheque audit fields end up inside
`section_tax_withholding_entry` (`depends_on: eval: doc.apply_tds`) and are
hidden while server-side validation still requires them.

Fix: delete the stale layout override. The core field order plus each custom
field's `insert_after` are authoritative again.

Idempotent: safe to re-run; no-op when the override is already gone.
Run position: [post_model_sync] - doctypes must be synced first.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import delete_property_setter


def execute():
	filters = {
		"doc_type": "Payment Entry",
		"property": "field_order",
		"field_name": ("is", "not set"),
	}
	if not frappe.db.exists("Property Setter", filters):
		return

	delete_property_setter("Payment Entry", "field_order")
	frappe.clear_cache(doctype="Payment Entry")
	frappe.logger().info("[fix_payment_entry_field_order] Removed stale field_order override.")
