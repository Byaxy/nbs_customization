# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""
Patch: backfill_placement_mirror_fields
---------------------------------------
Fills `pack_volume_ml` on draft Contract Test Reagent Line rows that predate
the field, copying the value from the matching linked-worksheet reagent line
(same item_code + test_parameter). The mirror guard enforces this field, so
without the backfill the next save of an old draft would reject it.

Design principles (mirrors backfill_placement_company):
  - Idempotent: only touches rows where pack_volume_ml IS NULL or 0.
  - Only draft contracts (docstatus = 0); submitted rows stay untouched.
  - Bulk SQL: no record-by-record loops.

Run position: [post_model_sync] — child table columns must already exist.
"""

import frappe


def execute():
	frappe.logger().info("[backfill_placement_mirror_fields] Starting mirror field backfill...")

	updated = frappe.db.sql(
		"""
		UPDATE `tabContract Test Reagent Line` child
		INNER JOIN `tabInstrument Placement Contract` ct
			ON ct.name = child.parent AND ct.docstatus = 0
			AND ct.pricing_worksheet IS NOT NULL AND ct.pricing_worksheet != ''
		INNER JOIN `tabWorksheet Test Reagent Line` ws
			ON ws.parent = ct.pricing_worksheet
			AND ws.item_code = child.item_code
			AND COALESCE(ws.test_parameter, '') = COALESCE(child.test_parameter, '')
		SET child.pack_volume_ml = ws.pack_volume_ml
		WHERE (child.pack_volume_ml IS NULL OR child.pack_volume_ml = 0)
			AND ws.pack_volume_ml IS NOT NULL AND ws.pack_volume_ml != 0
		"""
	)

	frappe.db.commit()
	frappe.logger().info(f"[backfill_placement_mirror_fields] Updated {updated or 0} row(s).")
