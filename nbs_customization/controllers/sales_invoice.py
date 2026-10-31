"""
Overrides for the standard Sales Invoice DocType.
Currently handles:
  - Denormalizing the linked Sales Order(s) up to the SI header
    so that custom_sales_order is available in the list view,
    standard filters, and reports without any JOIN queries.
  - Enabling tax withholding when the customer is configured for it.
"""

import frappe

# Hidden item-row marker: the category this app copied from the customer.
COPIED_CATEGORY_FIELD = "custom_copied_tax_withholding_category"

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

	Item-level categories drive ERPNext's withholding engine. Each item row
	records the category this app copied onto it, so customer changes update
	only derived rows and leave real item overrides alone. Opening entries
	are exempt, matching erpnext.
	"""
	if doc.get("is_opening") == "Yes":
		return

	withholding = _get_customer_withholding(doc.get("customer"))
	category = withholding.get("tax_withholding_category")

	if category or withholding.get("tax_withholding_group"):
		doc.apply_tds = 1

	for item in doc.get("items") or []:
		item_category = item.get("tax_withholding_category")
		copied_category = item.get(COPIED_CATEGORY_FIELD)

		if not item_category or (copied_category and item_category == copied_category):
			item.tax_withholding_category = category
			item.set(COPIED_CATEGORY_FIELD, category)
		elif doc.is_new() and item_category == category:
			# Core populated this row from the customer before the first save.
			item.set(COPIED_CATEGORY_FIELD, category)
		else:
			item.set(COPIED_CATEGORY_FIELD, None)


# ---------------------------------------------------------------------------
# Hook entry-points  (referenced in hooks.py → doc_events)
# ---------------------------------------------------------------------------


def before_validate(doc, method=None):
	_apply_customer_tax_withholding(doc)


def before_save(doc, method=None):
	_set_custom_sales_order(doc)


def before_submit(doc, method=None):
	"""
	Re-run on submit so that any last-minute item changes are captured.
	(before_save runs first, but being explicit here is safer for
	workflows that skip the save step before submission.)
	"""
	_set_custom_sales_order(doc)
