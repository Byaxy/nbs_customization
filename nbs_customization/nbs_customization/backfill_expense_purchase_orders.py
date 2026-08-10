# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt
"""
One-off backfill for the PO-based accompanying expense change.

Every Expense still carrying the legacy scope value 'Single Purchase Receipt'
is migrated to the new 'Single Purchase Order' scope, backfilling
linked_purchase_order from the linked Purchase Receipt's Purchase Order(s).

Rules:
  - linked_purchase already resolves to a Purchase Order  -> promoted as-is.
  - linked_purchase is a Purchase Receipt with exactly one distinct PO -> backfilled.
  - linked_purchase is a Purchase Receipt with no PO / multiple POs -> skipped (ambiguous).
  - linked_purchase is empty or the PR no longer exists -> skipped.

Run (dry-run first, then real):

    bench --site nbsolutions.localhost execute \
        nbs_customization.nbs_customization.backfill_expense_purchase_orders.run
    bench --site nbsolutions.localhost execute \
        nbs_customization.nbs_customization.backfill_expense_purchase_orders.run --kwargs '{"dry_run": false}'
"""

import frappe


def run(dry_run=True, commit=True):
	expenses = frappe.db.get_all(
		"Expense",
		filters={"expense_scope": "Single Purchase Receipt", "docstatus": ["in", [0, 1]]},
		fields=["name", "linked_purchase"],
		order_by="creation asc",
	)

	processed = 0
	skipped = {"missing_link": [], "missing_pr": [], "no_po": [], "multi_po": []}

	for expense in expenses:
		link = (expense.linked_purchase or "").strip()
		if not link:
			skipped["missing_link"].append(expense.name)
			continue

		if frappe.db.exists("Purchase Order", link):
			po = link
		elif frappe.db.exists("Purchase Receipt", link):
			po_rows = frappe.db.get_all(
				"Purchase Receipt Item",
				filters={"parent": link, "purchase_order": ["is", "set"]},
				fields=["purchase_order"],
			)
			pos = sorted({row["purchase_order"] for row in po_rows})
			if not pos:
				skipped["no_po"].append(f"{expense.name} (PR {link})")
				continue
			if len(pos) > 1:
				skipped["multi_po"].append(f"{expense.name} (PR {link} -> {', '.join(pos)})")
				continue
			po = pos[0]
		else:
			skipped["missing_pr"].append(f"{expense.name} (PR {link})")
			continue

		processed += 1
		if dry_run:
			continue

		frappe.db.set_value(
			"Expense",
			expense.name,
			{"expense_scope": "Single Purchase Order", "linked_purchase_order": po},
		)

	if not dry_run and commit:
		frappe.db.commit()

	print(f"Backfill {'DRY RUN -' if dry_run else ''} summary: {len(expenses)} matched")
	print(f"  processed: {processed}")
	for key, items in skipped.items():
		print(f"  skipped ({key}): {len(items)}")
		for item in items[:10]:
			print(f"    - {item}")
		if len(items) > 10:
			print(f"    ... and {len(items) - 10} more")

	return {"processed": processed, "skipped": {k: len(v) for k, v in skipped.items()}}
