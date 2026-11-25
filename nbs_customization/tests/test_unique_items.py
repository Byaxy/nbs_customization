import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from nbs_customization.controllers.validations.sales import validate_unique_items
from nbs_customization.tests.sales_doubles import COMPANY, ensure_test_item

UNIQUE_ITEMS_JS = Path(__file__).resolve().parents[1] / "public/js/nbs_unique_items.js"


def _run_js_duplicate_rows(items):
	script = (
		"global.frappe = { ui: { form: { on() {} } }, utils: { escape_html: (text) => text }, msgprint() {} };\n"
		"global.__ = (text) => text;\n"
		+ UNIQUE_ITEMS_JS.read_text()
		+ f"\nconsole.log(JSON.stringify(nbs_duplicate_item_rows({{ doc: {{ items: {json.dumps(items)} }} }})));\n"
	)
	result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
	return json.loads(result.stdout)


def _make_supplier(name):
	return (
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": name,
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
				or "All Supplier Groups",
				"supplier_type": "Company",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _make_customer(name):
	return (
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
				or "All Customer Groups",
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _warehouse():
	return frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 0}, "name")


def _naming_series(doctype):
	return next(
		line
		for line in frappe.get_meta(doctype).get_field("naming_series").options.splitlines()
		if line.strip()
	)


def _item_rows(item_codes):
	uom = frappe.db.get_value("Item", item_codes[0], "stock_uom") or "Nos"
	return [
		{
			"item_code": item_code,
			"qty": 1,
			"rate": 100,
			"uom": uom,
			"stock_uom": uom,
			"conversion_factor": 1,
			"warehouse": _warehouse(),
			"schedule_date": today(),
		}
		for item_code in item_codes
	]


def _sales_item_rows(item_codes):
	uom = frappe.db.get_value("Item", item_codes[0], "stock_uom") or "Nos"
	return [
		{
			"item_code": item_code,
			"item_name": frappe.db.get_value("Item", item_code, "item_name") or item_code,
			"qty": 1,
			"rate": 100,
			"uom": uom,
			"stock_uom": uom,
			"conversion_factor": 1,
			"warehouse": _warehouse(),
		}
		for item_code in item_codes
	]


def _make_quotation(item_codes):
	items = _sales_item_rows(item_codes)
	for row in items:
		row["ordered_qty"] = 0

	return frappe.get_doc(
		{
			"doctype": "Quotation",
			"company": COMPANY,
			"quotation_to": "Customer",
			"party_name": _make_customer("_Test Unique Customer"),
			"transaction_date": today(),
			"naming_series": _naming_series("Quotation"),
			"currency": frappe.db.get_value("Company", COMPANY, "default_currency") or "USD",
			"conversion_rate": 1,
			"custom_request_for_quotation_number": "TEST-RFQ-0001",
			"items": items,
		}
	).insert()


def _make_sales_order(item_codes):
	return frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": COMPANY,
			"customer": _make_customer("_Test Unique Customer"),
			"transaction_date": today(),
			"delivery_date": today(),
			"currency": frappe.db.get_value("Company", COMPANY, "default_currency") or "USD",
			"conversion_rate": 1,
			"items": _sales_item_rows(item_codes),
		}
	).insert()


def _make_rfq(item_codes):
	return frappe.get_doc(
		{
			"doctype": "Request for Quotation",
			"company": COMPANY,
			"transaction_date": today(),
			"naming_series": _naming_series("Request for Quotation"),
			"suppliers": [{"supplier": _make_supplier("_Test RFQ Unique Supplier")}],
			"items": _item_rows(item_codes),
		}
	).insert()


def _make_purchase_order(item_codes):
	return frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"company": COMPANY,
			"supplier": _make_supplier("_Test PO Unique Supplier"),
			"transaction_date": today(),
			"schedule_date": today(),
			"naming_series": _naming_series("Purchase Order"),
			"items": _item_rows(item_codes),
		}
	).insert()


class TestUniqueItems(IntegrationTestCase):
	def test_rfq_rejects_duplicate_item_code(self):
		item_code = ensure_test_item()

		with self.change_settings("Buying Settings", {"allow_multiple_items": 0}):
			with self.assertRaises(frappe.ValidationError) as raised:
				_make_rfq([item_code, item_code])

		message = str(raised.exception)
		self.assertIn(item_code, message)
		self.assertIn("rows #1, #2", message)
		self.assertIn("Combine the quantities", message)

	def test_rfq_allows_distinct_items(self):
		rfq = _make_rfq([ensure_test_item(), ensure_test_item("_Test Buying Item B")])

		self.assertEqual(len(rfq.items), 2)

	def test_purchase_order_rejects_duplicate_item_code(self):
		item_code = ensure_test_item()

		with self.change_settings("Buying Settings", {"allow_multiple_items": 0}):
			with self.assertRaises(frappe.ValidationError) as raised:
				_make_purchase_order([item_code, item_code])

		message = str(raised.exception)
		self.assertIn(item_code, message)
		self.assertIn("rows #1, #2", message)
		self.assertIn("Combine the quantities", message)

	def test_purchase_order_allows_distinct_items(self):
		po = _make_purchase_order([ensure_test_item(), ensure_test_item("_Test Buying Item B")])

		self.assertEqual(len(po.items), 2)

	def test_quotation_rejects_duplicate_item_code(self):
		item_code = ensure_test_item()

		with self.change_settings("Selling Settings", {"allow_multiple_items": 0}):
			with self.assertRaises(frappe.ValidationError) as raised:
				_make_quotation([item_code, item_code])

		message = str(raised.exception)
		self.assertIn(item_code, message)
		self.assertIn("rows #1, #2", message)
		self.assertIn("Combine the quantities", message)

	def test_sales_order_rejects_duplicate_item_code(self):
		item_code = ensure_test_item()

		with self.change_settings("Selling Settings", {"allow_multiple_items": 0}):
			with self.assertRaises(frappe.ValidationError) as raised:
				_make_sales_order([item_code, item_code])

		message = str(raised.exception)
		self.assertIn(item_code, message)
		self.assertIn("rows #1, #2", message)
		self.assertIn("Combine the quantities", message)

	def test_js_helper_handles_prototype_item_codes(self):
		duplicates = _run_js_duplicate_rows(
			[
				{"item_code": "constructor", "idx": 1},
				{"item_code": "toString", "idx": 2},
				{"item_code": "toString", "idx": 3},
				{"item_code": "__proto__", "idx": 4},
				{"item_code": "__proto__", "idx": 5},
				{"item_code": "hasOwnProperty", "idx": 6},
			]
		)

		self.assertEqual(duplicates, [["toString", ["#2", "#3"]], ["__proto__", ["#4", "#5"]]])

	def test_ignore_validate_flag_skips_check(self):
		validate_unique_items(
			SimpleNamespace(
				flags=SimpleNamespace(ignore_validate=True),
				items=[
					frappe._dict(item_code="ITEM-A", idx=1),
					frappe._dict(item_code="ITEM-A", idx=2),
				],
			)
		)

	def test_message_lists_every_duplicate_item_and_row(self):
		doc = SimpleNamespace(
			items=[
				frappe._dict(item_code="ITEM-A", idx=1),
				frappe._dict(item_code="ITEM-B", idx=2),
				frappe._dict(item_code="ITEM-A", idx=3),
				frappe._dict(item_code="ITEM-B", idx=4),
			]
		)

		with self.assertRaises(frappe.ValidationError) as raised:
			validate_unique_items(doc)

		message = str(raised.exception)
		self.assertIn("ITEM-A", message)
		self.assertIn("rows #1, #3", message)
		self.assertIn("ITEM-B", message)
		self.assertIn("rows #2, #4", message)
		self.assertIn("Combine the quantities", message)
