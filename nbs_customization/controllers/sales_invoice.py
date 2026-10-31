"""
Overrides for the standard Sales Invoice DocType.
Currently handles:
  - Denormalizing the linked Sales Order(s) up to the SI header
    so that custom_sales_order is available in the list view,
    standard filters, and reports without any JOIN queries.
  - Enabling tax withholding when the customer is configured for it.
"""

import frappe

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_sales_orders(doc):
	"""
	Return a de-duplicated, ordered list of Sales Order names
	referenced across all SI items.  Order is preserved (first seen first).
	"""
	seen = set()
	orders = []
	for item in doc.items:
		so = item.get("sales_order")
		if so and so not in seen:
			seen.add(so)
			orders.append(so)
	return orders


def _set_custom_sales_order(doc):
	"""
	Populate custom_sales_order on the SI header.

	Rules
	-----
	- Single SO  →  store that SO name (normal Link behaviour).
	- Multiple SOs → store the first SO found.
	  The field label will get a visual note appended via the list JS
	  so users know there are additional SOs on the form.
	- No SO at all (e.g. direct sales invoice) → clear the field.
	"""
	orders = _collect_sales_orders(doc)

	if orders:
		doc.custom_sales_order = orders[0]
	else:
		doc.custom_sales_order = None


def _get_customer_withholding(customer):
	if not customer:
		return {}

	return (
		frappe.get_cached_value(
			"Customer",
			customer,
			["tax_withholding_category", "tax_withholding_group"],
			as_dict=True,
		)
		or {}
	)


def _apply_customer_tax_withholding(doc):
	"""
	Withhold tax whenever the customer is configured for it.

	Item-level categories drive ERPNext's withholding engine, so copy the
	customer category into rows that do not carry their own. Opening entries
	are exempt, matching erpnext's own controller.
	"""
	if doc.get("is_opening") == "Yes":
		return

	withholding = _get_customer_withholding(doc.get("customer"))
	category = withholding.get("tax_withholding_category")

	if not (category or withholding.get("tax_withholding_group")):
		return

	doc.apply_tds = 1

	if not category:
		return

	for item in doc.get("items") or []:
		if not item.get("tax_withholding_category"):
			item.tax_withholding_category = category


# ---------------------------------------------------------------------------
# Hook entry-points  (referenced in hooks.py → doc_events)
# ---------------------------------------------------------------------------


def before_save(doc, method=None):
	_set_custom_sales_order(doc)
	_apply_customer_tax_withholding(doc)


def before_submit(doc, method=None):
	"""
	Re-run on submit so that any last-minute item changes are captured.
	(before_save runs first, but being explicit here is safer for
	workflows that skip the save step before submission.)
	"""
	_set_custom_sales_order(doc)
