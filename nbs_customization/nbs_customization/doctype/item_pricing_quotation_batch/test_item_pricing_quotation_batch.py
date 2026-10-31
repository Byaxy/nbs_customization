# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from nbs_customization.utils.pricing import get_current_selling_price

ITEM = "_Test Pricing Batch Item"

FIXED_PRICE_LISTS = [
	"Standard Selling",
	"Selling - Basic",
	"Selling - 15%",
	"Selling - 30%",
	"Selling - 45%",
	"Selling - Commission",
	"Selling - Commission (Tax)",
]


class IntegrationTestItemPricingQuotationBatch(IntegrationTestCase):
	def setUp(self):
		_ensure_item()
		for name in FIXED_PRICE_LISTS:
			_ensure_price_list(name)
		if frappe.db.exists("Item Pricing Settings", ITEM):
			frappe.delete_doc("Item Pricing Settings", ITEM, force=1, ignore_permissions=True)

	def test_batch_syncs_current_selling_price_from_standard_selling(self):
		company = _company()
		if not company:
			self.skipTest("No company available for batch setup.")

		batch = frappe.get_doc(
			{
				"doctype": "Item Pricing Quotation Batch",
				"naming_series": "NBSQT-.YYYY.-.####",
				"company": company,
				"posting_date": today(),
				"standard_selling_source_tier": "30%",
				"items": [{"item_code": ITEM, "qty": 1, "unit_cost": 100}],
			}
		)
		batch.insert(ignore_permissions=True)
		batch.submit()

		settings = frappe.get_doc("Item Pricing Settings", ITEM)
		live = get_current_selling_price(ITEM)
		self.assertGreater(flt(live), 0)
		self.assertEqual(flt(settings.current_selling_price), flt(live))
		self.assertEqual(flt(settings.rate_30), flt(live))


def _ensure_item():
	if frappe.db.exists("Item", ITEM):
		return
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": ITEM,
			"item_name": ITEM,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "Products",
			"stock_uom": _uom(),
			"is_stock_item": 0,
		}
	).insert(ignore_permissions=True)


def _ensure_price_list(name):
	if frappe.db.exists("Price List", name):
		return
	frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": name,
			"selling": 1,
			"buying": 0,
			"currency": _currency(),
		}
	).insert(ignore_permissions=True)


def _company():
	return frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value(
		"Company", {}, "name"
	)


def _currency():
	company = _company()
	currency = frappe.get_cached_value("Company", company, "default_currency") if company else None
	return currency or frappe.db.get_value("Currency", {}, "name") or "USD"


def _uom():
	return frappe.db.get_value("UOM", {}, "name") or "Nos"
