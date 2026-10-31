# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import cint, flt

from nbs_customization.nbs_customization.doctype.item_pricing_settings.item_pricing_settings import (
	get_item_live_rates,
	refresh_valuation,
)
from nbs_customization.utils.pricing import recompute_suggested_price

ITEM = "_Test Pricing Settings Item"


class IntegrationTestItemPricingSettings(IntegrationTestCase):
	def setUp(self):
		_ensure_item()
		_ensure_price_list("Standard Selling")
		_ensure_price_list("Selling - 30%")
		_clear_settings()

	def test_auto_recompute_uses_valuation_and_standard_selling(self):
		_set_item_price("Selling - 30%", 111)
		_set_item_price("Standard Selling", 222)
		_make_settings("Auto")

		with patch("nbs_customization.utils.pricing.get_current_valuation_rate", return_value=100):
			recompute_suggested_price(ITEM)

		doc = frappe.get_doc("Item Pricing Settings", ITEM)
		self.assertEqual(flt(doc.current_valuation_rate), 100)
		self.assertEqual(flt(doc.rate_30), 142.86)
		self.assertEqual(flt(doc.current_selling_price), 222)

	def test_pinned_valuation_survives_receipt_refresh(self):
		_set_item_price("Standard Selling", 300)
		_make_settings("Auto")

		doc = frappe.get_doc("Item Pricing Settings", ITEM)
		doc.valuation_rate_override = 1
		doc.current_valuation_rate = 120
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(flt(doc.rate_30), 171.43)

		with patch("nbs_customization.utils.pricing.get_current_valuation_rate", return_value=150):
			recompute_suggested_price(ITEM)

		doc.reload()
		self.assertEqual(flt(doc.current_valuation_rate), 120)
		self.assertEqual(flt(doc.rate_30), 171.43)

	def test_refresh_valuation_unpins_and_uses_latest_sle(self):
		_set_item_price("Standard Selling", 300)
		_make_settings("Auto")

		doc = frappe.get_doc("Item Pricing Settings", ITEM)
		doc.valuation_rate_override = 1
		doc.current_valuation_rate = 120
		doc.save(ignore_permissions=True)

		with patch("nbs_customization.utils.pricing.get_current_valuation_rate", return_value=150):
			refresh_valuation(ITEM)

		doc.reload()
		self.assertEqual(flt(doc.current_valuation_rate), 150)
		self.assertEqual(cint(doc.valuation_rate_override), 0)
		self.assertEqual(flt(doc.rate_30), 214.29)

	def test_manual_refresh_reads_standard_selling(self):
		_set_item_price("Selling - 30%", 111)
		_set_item_price("Standard Selling", 222)
		_make_settings("Manual", estimated_base_rate=100, manual_qty=1)

		refresh_valuation(ITEM)

		doc = frappe.get_doc("Item Pricing Settings", ITEM)
		self.assertEqual(flt(doc.current_selling_price), 222)

	def test_get_item_live_rates_returns_sle_and_standard_selling(self):
		_set_item_price("Standard Selling", 222)

		with patch(
			"nbs_customization.nbs_customization.doctype.item_pricing_settings.item_pricing_settings.get_current_valuation_rate",
			return_value=100,
		):
			rates = get_item_live_rates(ITEM)

		self.assertEqual(flt(rates["current_valuation_rate"]), 100)
		self.assertEqual(flt(rates["current_selling_price"]), 222)

	def test_get_item_live_rates_returns_zero_for_missing_item(self):
		self.assertEqual(
			get_item_live_rates(""), {"current_valuation_rate": 0.0, "current_selling_price": 0.0}
		)
		self.assertEqual(
			get_item_live_rates(None), {"current_valuation_rate": 0.0, "current_selling_price": 0.0}
		)


def _make_settings(mode, **values):
	_clear_settings()
	doc = frappe.get_doc(
		{
			"doctype": "Item Pricing Settings",
			"item_code": ITEM,
			"pricing_mode": mode,
			"standard_selling_source_tier": "30%",
			**values,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _clear_settings():
	if frappe.db.exists("Item Pricing Settings", ITEM):
		frappe.delete_doc("Item Pricing Settings", ITEM, force=1, ignore_permissions=True)


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


def _set_item_price(price_list, rate):
	existing = frappe.db.get_value(
		"Item Price", {"item_code": ITEM, "price_list": price_list, "selling": 1}, "name"
	)
	if existing:
		frappe.db.set_value("Item Price", existing, "price_list_rate", rate)
		return
	frappe.get_doc(
		{
			"doctype": "Item Price",
			"item_code": ITEM,
			"price_list": price_list,
			"price_list_rate": rate,
			"currency": _currency(),
			"uom": _uom(),
			"selling": 1,
			"buying": 0,
		}
	).insert(ignore_permissions=True)


def _currency():
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	currency = frappe.get_cached_value("Company", company, "default_currency") if company else None
	return currency or frappe.db.get_value("Currency", {}, "name") or "USD"


def _uom():
	return frappe.db.get_value("UOM", {}, "name") or "Nos"
