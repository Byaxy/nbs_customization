# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, today
from nbs_customization.utils.pricing import recompute_suggested_price


class ItemPricingSettings(Document):

	def validate(self):
		self._validate_margin()
		self._validate_no_duplicate()

	# ------------------------------------------------------------------ #
	#  Validation                                                           #
	# ------------------------------------------------------------------ #

	def _validate_margin(self):
		margin = flt(self.target_margin_pct)
		if margin <= 0:
			frappe.throw("Target Margin must be greater than 0%.")
		if margin >= 100:
			frappe.throw("Target Margin must be less than 100%.")

	def _validate_no_duplicate(self):
		# autoname = field:item_code already enforces uniqueness at the DB
		# level, but this gives a cleaner error message during creation.
		if self.is_new():
			if frappe.db.exists("Item Pricing Settings", self.item_code):
				frappe.throw(
					f"A pricing settings record already exists for {self.item_code}. "
					"Open that record to make changes."
				)

# ------------------------------------------------------------------ #
#  Actions (called from JS buttons)                                     #
# ------------------------------------------------------------------ #
@frappe.whitelist()
def refresh_valuation(doc_name):
	recompute_suggested_price(doc_name)
	frappe.msgprint(
		"Valuation rate refreshed. Review the suggested price below.",
		indicator="blue",
		alert=True,
	)


@frappe.whitelist()
def apply_suggested_price(doc_name):
	doc = frappe.get_doc("Item Pricing Settings", doc_name)

	if not flt(doc.suggested_selling_price):
		frappe.throw(
			"Suggested Selling Price is zero. "
			"Click Refresh Valuation before applying."
		)

	price_list = doc.price_list or "Standard Selling"
	new_rate = flt(doc.suggested_selling_price, 2)
	currency = frappe.get_cached_value("Price List", price_list, "currency")
	uom = (
		frappe.get_cached_value("Item", doc.item_code, "sales_uom")
		or frappe.get_cached_value("Item", doc.item_code, "stock_uom")
	)

	existing = frappe.db.get_value(
		"Item Price",
		{
			"item_code": doc.item_code,
			"price_list": price_list,
			"selling": 1,
		},
		"name",
	)

	if existing:
		frappe.db.set_value(
			"Item Price",
			existing,
			{
				"price_list_rate": new_rate,
				"currency": currency,
				"valid_from": today(),
			},
			update_modified=True,
		)
	else:
		frappe.get_doc({
			"doctype": "Item Price",
			"item_code": doc.item_code,
			"price_list": price_list,
			"price_list_rate": new_rate,
			"currency": currency,
			"uom": uom,
			"valid_from": today(),
			"selling": 1,
			"buying": 0,
		}).insert(ignore_permissions=True)

	frappe.db.set_value(
		"Item Pricing Settings",
		doc_name,
		"current_selling_price",
		new_rate,
		update_modified=False,
	)
	frappe.db.commit()

	frappe.msgprint(
		f"Selling price of <b>{currency} {new_rate}</b> applied to "
		f"<b>{doc.item_code}</b> under <b>{price_list}</b>.",
		title="Price Applied",
		indicator="green",
	)