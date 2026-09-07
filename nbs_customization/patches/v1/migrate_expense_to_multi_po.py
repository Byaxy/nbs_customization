# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""
Patch: migrate_expense_to_multi_po
-----------------------------------
Migrates Expense.linked_purchase_order (single Link) into
Expense Purchase Order child table (purchase_orders).

For every Expense where linked_purchase_order is set and
no child rows exist, inserts one child row with that PO.
Preserves legacy field for back-compat. Idempotent.
"""

import frappe


def execute():
	frappe.logger().info("[migrate_expense_to_multi_po] Starting...")

	# Ensure child table exists (already via migrate)
	expenses = frappe.db.get_all(
		"Expense",
		filters={"linked_purchase_order": ["is", "set"]},
		fields=["name", "linked_purchase_order"],
	)

	migrated = 0
	skipped = 0

	for exp in expenses:
		po = exp.linked_purchase_order
		if not po:
			skipped += 1
			continue
		# Check if child already has this PO
		exists = frappe.db.exists("Expense Purchase Order", {"parent": exp.name, "purchase_order": po})
		if exists:
			skipped += 1
			continue

		# Check if any child rows exist at all
		count = frappe.db.count("Expense Purchase Order", {"parent": exp.name})
		if count > 0:
			# Already migrated via other PO, keep legacy synced to first child
			skipped += 1
			continue

		# Insert child row directly (bypass validate to avoid recursion)
		# Fetch display fields for child
		po_data = frappe.db.get_value(
			"Purchase Order", po, ["supplier", "transaction_date", "grand_total", "status"], as_dict=True
		)
		doc = frappe.get_doc(
			{
				"doctype": "Expense Purchase Order",
				"parent": exp.name,
				"parenttype": "Expense",
				"parentfield": "purchase_orders",
				"purchase_order": po,
				"supplier": po_data.supplier if po_data else None,
				"transaction_date": po_data.transaction_date if po_data else None,
				"grand_total": po_data.grand_total if po_data else 0,
				"status": po_data.status if po_data else None,
			}
		)
		doc.insert(ignore_permissions=True)
		migrated += 1
		frappe.logger().info(f"[migrate_expense_to_multi_po] {exp.name} -> {po}")

	frappe.db.commit()
	frappe.logger().info(f"[migrate_expense_to_multi_po] Done. migrated={migrated} skipped={skipped}")
