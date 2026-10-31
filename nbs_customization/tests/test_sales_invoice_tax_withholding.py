# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, today

from nbs_customization.tests.sales_doubles import COMPANY, make_test_sales_invoice

CATEGORY = "_Test SI Withholding Category"
CUSTOMER_WITH = "_Test SI Withholding Customer"
CUSTOMER_WITHOUT = "_Test SI No Withholding Customer"


def _ensure_category():
	if frappe.db.exists("Tax Withholding Category", CATEGORY):
		return CATEGORY

	frappe.get_doc(
		{
			"doctype": "Tax Withholding Category",
			"name": CATEGORY,
			"category_name": CATEGORY,
			"tax_deduction_basis": "Net Total",
			"rates": [
				{
					"from_date": add_days(today(), -365),
					"to_date": add_days(today(), 365),
					"tax_withholding_rate": 10,
					"single_threshold": 0,
					"cumulative_threshold": 0,
				}
			],
			"accounts": [{"company": COMPANY, "account": "Accrued Expenses - _TC"}],
		}
	).insert(ignore_permissions=True)
	return CATEGORY


def _ensure_customer(name, category=None):
	if frappe.db.exists("Customer", name):
		if category:
			frappe.get_doc("Customer", name).db_set("tax_withholding_category", category)
		return name

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Company",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			"tax_withholding_category": category,
		}
	)
	customer.insert(ignore_permissions=True)
	return customer.name


class TestSalesInvoiceTaxWithholding(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		category = _ensure_category()
		self.customer_with = _ensure_customer(CUSTOMER_WITH, category)
		self.customer_without = _ensure_customer(CUSTOMER_WITHOUT)

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
