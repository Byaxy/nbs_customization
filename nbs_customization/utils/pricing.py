import frappe
from frappe.utils import flt, now_datetime


def recompute_suggested_price(item_code):
	"""
	Reads the current valuation rate for item_code from the most recent
	Stock Ledger Entry, then updates the Item Pricing Settings record with:
	  - current_valuation_rate
	  - suggested_selling_price
	  - current_selling_price  (what is currently live in Item Price)
	  - last_updated

	Does NOT write to Item Price. That is a deliberate manual step
	performed by the pricing manager via the Apply button on the form.

	Silently skips if no Item Pricing Settings record exists for the item,
	so this function will never block a Purchase Receipt or LCV submission.
	"""
	settings_name = frappe.db.get_value(
		"Item Pricing Settings", {"item_code": item_code}, "name"
	)
	if not settings_name:
		return

	settings = frappe.db.get_value(
		"Item Pricing Settings",
		settings_name,
		["target_margin_pct", "price_list"],
		as_dict=True,
	)

	margin_pct = flt(settings.target_margin_pct)
	if not margin_pct or margin_pct <= 0 or margin_pct >= 100:
		return

	val_rate = _get_current_valuation_rate(item_code)
	if not val_rate:
		return

	margin = margin_pct / 100
	suggested_sp = flt(val_rate) / (1 - margin)

	price_list = settings.price_list or "Standard Selling"
	current_sp = flt(
		frappe.db.get_value(
			"Item Price",
			{
				"item_code": item_code,
				"price_list": price_list,
				"selling": 1,
			},
			"price_list_rate",
		)
	)

	frappe.db.set_value(
		"Item Pricing Settings",
		settings_name,
		{
			"current_valuation_rate": flt(val_rate, 4),
			"suggested_selling_price": flt(suggested_sp, 2),
			"current_selling_price": flt(current_sp, 2),
			"last_updated": now_datetime(),
		},
		update_modified=False,
	)


def _get_current_valuation_rate(item_code):
	"""
	Returns the valuation rate from the most recent inbound Stock Ledger
	Entry for the item. This is ERPNext's own computed rate — moving average
	or FIFO — after the latest receipt or LCV adjustment. Reading from SLE
	is more reliable than reading from Bin because Bin aggregates across
	warehouses and can lag briefly after an LCV submission.
	"""
	result = frappe.db.get_value(
		"Stock Ledger Entry",
		{
			"item_code": item_code,
			"is_cancelled": 0,
			"actual_qty": [">", 0],
		},
		"valuation_rate",
		order_by="posting_date desc, posting_time desc, creation desc",
	)
	return flt(result)


def on_purchase_receipt_submit(doc, method=None):
	"""
	doc_events trigger — fires when a Purchase Receipt is submitted.
	Recomputes suggested prices for every item on the receipt.
	Each item is wrapped in its own try/except so one bad item
	never blocks the others or the receipt itself.
	"""
	item_codes = list({row.item_code for row in doc.items})
	for item_code in item_codes:
		try:
			recompute_suggested_price(item_code)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Pricing recompute failed: {item_code} (PR: {doc.name})",
			)


def on_landed_cost_voucher_submit(doc, method=None):
	"""
	doc_events trigger — fires when a Landed Cost Voucher is submitted.
	LCV submission is exactly the moment the valuation rate settles to its
	final value, so this is the most important trigger of the two.
	"""
	item_codes = list({row.item_code for row in doc.items})
	for item_code in item_codes:
		try:
			recompute_suggested_price(item_code)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Pricing recompute failed: {item_code} (LCV: {doc.name})",
			)