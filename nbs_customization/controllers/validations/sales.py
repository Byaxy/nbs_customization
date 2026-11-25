import frappe


def validate_unique_items(doc, method=None):
	flags = getattr(doc, "flags", None)
	if flags and getattr(flags, "ignore_validate", False):
		return

	rows_by_item = {}

	for row in doc.items:
		if not row.item_code:
			continue
		rows_by_item.setdefault(row.item_code, []).append(f"#{row.idx}")

	duplicates = [(item_code, rows) for item_code, rows in rows_by_item.items() if len(rows) > 1]
	if not duplicates:
		return

	details = "".join(
		f"<li>{frappe.bold(item_code)}: rows {', '.join(rows)}</li>" for item_code, rows in duplicates
	)
	frappe.throw(
		frappe._("Each item must appear on only one row. Combine the quantities for:")
		+ f"<ul>{details}</ul>",
		title=frappe._("Duplicate Items"),
	)


def prepare_quotation_test_record(doc, method=None):
	"""Test records built by the framework skip the app's mandatory RFQ number."""
	if not doc.custom_request_for_quotation_number:
		doc.custom_request_for_quotation_number = "TEST-RFQ-0001"
