# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from nbs_customization.tests.sales_doubles import (
	COMPANY,
	ensure_test_item,
	make_test_sales_invoice,
)

CATEGORY = "_Test SI Withholding Category"
CATEGORY_ALT = "_Test SI Withholding Category Alt"
CATEGORY_OVERRIDE = "_Test SI Withholding Category Override"
CUSTOMER_WITH = "_Test SI Withholding Customer"
CUSTOMER_ALT = "_Test SI Withholding Customer Alt"
CUSTOMER_WITHOUT = "_Test SI No Withholding Customer"


def _ensure_category(name, rate=10):
	if frappe.db.exists("Tax Withholding Category", name):
		return name

	frappe.get_doc(
		{
			"doctype": "Tax Withholding Category",
			"name": name,
			"category_name": name,
			"tax_deduction_basis": "Net Total",
			"rates": [
				{
					"from_date": add_days(today(), -365),
					"to_date": add_days(today(), 365),
					"tax_withholding_rate": rate,
					"single_threshold": 0,
					"cumulative_threshold": 0,
				}
			],
			"accounts": [{"company": COMPANY, "account": "Accrued Expenses - _TC"}],
		}
	).insert(ignore_permissions=True)
	return name


def _ensure_customer(name, category=None):
	if frappe.db.exists("Customer", name):
		doc = frappe.get_doc("Customer", name)
		if category:
			doc.db_set("tax_withholding_category", category)
		doc.db_set("so_required", 1)
		return name

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Company",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			"tax_withholding_category": category,
			"so_required": 1,
		}
	)
	customer.insert(ignore_permissions=True)
	return customer.name


def _account(name, **filters):
	return frappe.db.get_value("Account", {"name": name, "company": COMPANY, **filters}, "name")


def _make_draft(customer):
	item_code = ensure_test_item()
	uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"

	si = frappe.new_doc("Sales Invoice")
	si.set_posting_time = 1
	si.posting_date = today()
	si.company = COMPANY
	si.customer = customer
	si.debit_to = _account("Debtors - _TC", account_type="Receivable")
	si.currency = frappe.db.get_value("Company", COMPANY, "default_currency") or "USD"
	si.conversion_rate = 1
	si.append(
		"items",
		{
			"item_code": item_code,
			"qty": 1,
			"uom": uom,
			"stock_uom": uom,
			"rate": 100,
			"price_list_rate": 100,
			"income_account": _account("Sales - _TC", root_type="Income", is_group=0),
			"expense_account": _account("Cost of Goods Sold - _TC", root_type="Expense", is_group=0),
			"cost_center": frappe.db.get_value("Cost Center", {"company": COMPANY, "is_group": 0}, "name"),
			"conversion_factor": 1,
		},
	)
	si.insert(ignore_permissions=True)
	return si


class TestSalesInvoiceTaxWithholding(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		category = _ensure_category(CATEGORY)
		category_alt = _ensure_category(CATEGORY_ALT, 5)
		self.category_override = _ensure_category(CATEGORY_OVERRIDE, 3)
		self.customer_with = _ensure_customer(CUSTOMER_WITH, category)
		self.customer_alt = _ensure_customer(CUSTOMER_ALT, category_alt)
		self.customer_without = _ensure_customer(CUSTOMER_WITHOUT)

	def _draft(self, customer):
		return _make_draft(customer)

	def test_customer_category_enables_withholding(self):
		si = make_test_sales_invoice(posting_date=today(), customer=self.customer_with)

		self.assertEqual(si.apply_tds, 1)
		self.assertEqual({item.tax_withholding_category for item in si.items}, {CATEGORY})
		self.assertTrue(si.tax_withholding_entries)
		self.assertTrue(any(flt(entry.withholding_amount) for entry in si.tax_withholding_entries))

	def test_customer_without_category_keeps_withholding_off(self):
		si = make_test_sales_invoice(posting_date=today(), customer=self.customer_without)

		self.assertFalse(si.apply_tds)
		self.assertFalse(si.tax_withholding_entries)

	def test_draft_save_applies_withholding(self):
		si = self._draft(self.customer_with)

		self.assertEqual(si.apply_tds, 1)
		self.assertEqual({item.tax_withholding_category for item in si.items}, {CATEGORY})
		self.assertTrue(si.tax_withholding_entries)

	def test_customer_change_refreshes_copied_category(self):
		si = self._draft(self.customer_with)
		si.customer = self.customer_alt
		si.save()

		self.assertEqual({item.tax_withholding_category for item in si.items}, {CATEGORY_ALT})
		self.assertEqual(
			{entry.tax_withholding_category for entry in si.tax_withholding_entries},
			{CATEGORY_ALT},
		)

	def test_customer_change_to_without_category_clears_copied_category(self):
		si = self._draft(self.customer_with)
		si.customer = self.customer_without
		si.save()

		self.assertFalse(any(item.tax_withholding_category for item in si.items))
		self.assertFalse(si.tax_withholding_entries)

	def test_customer_change_preserves_item_override(self):
		si = self._draft(self.customer_with)
		si.items[0].tax_withholding_category = self.category_override
		si.customer = self.customer_alt
		si.save()

		self.assertEqual(
			{entry.tax_withholding_category for entry in si.tax_withholding_entries},
			{self.category_override},
		)
