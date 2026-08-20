# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestContractLifecycle(FrappeTestCase):
	def setUp(self):
		self.analyzer = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST CL Analyzer", "item_group": "Products",
			 "is_stock_item": 1}
		).insert(ignore_if_duplicate=True)

		self.capital_item = frappe.get_doc({
			"doctype": "Item", "item_code": "_TST CL Capital Asset", "item_group": "Products",
			"is_fixed_asset": 1, "is_stock_item": 0, "asset_category": "Equipment",
		}).insert(ignore_if_duplicate=True)
		at = frappe.get_doc(
			{"doctype": "Analyzer Type", "title": "_TST CL Chem"}
		).insert(ignore_if_duplicate=True)
		self.reagent = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST CL Reagent", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc({
			"doctype": "Reagent Specification",
			"item": self.reagent.item_code,
			"reagent_role": "Test Reagent",
			"default_cogs_per_pack": 50,
			"default_tests_per_pack": 100,
		}).insert(ignore_if_duplicate=True)

		self.param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST CL Param", "parameter_code": "CL"}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc({
			"doctype": "Instrument Specification",
			"item": self.analyzer.item_code,
			"analyzer_type": at.name,
			"supported_test_methods": [{
				"test_parameter": self.param.name,
				"required_reagent": self.reagent.item_code,
			}],
		}).insert(ignore_if_duplicate=True)

		self.customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "_TST CL Customer", "customer_type": "Company"
		}).insert(ignore_if_duplicate=True)

		self.test_asset = frappe.get_doc({
			"doctype": "Asset", "asset_name": "_TST CL Asset",
			"item_code": self.capital_item.item_code,
			"company": "Northland Biomedical Solutions",
			"gross_purchase_amount": 5000,
			"net_purchase_amount": 5000,
			"asset_category": "Equipment",
			"location": "Block 1",
			"purchase_date": frappe.utils.today(),
		}).insert(ignore_if_duplicate=True)
		self.test_asset.db_set("custom_serial_no", "TST-001")

		self.test_site = frappe.get_doc({
			"doctype": "Address", "address_title": "_TST CL Site", "address_type": "Office",
			"address_line1": "123 Test St", "city": "Test City",
		}).insert(ignore_if_duplicate=True)

		ws = frappe.get_doc({
			"doctype": "Instrument Pricing Worksheet",
			"analyzer_pid": self.analyzer.item_code,
			"contract_type": "RRA",
			"calculation_output_type": "Markup Factor on Reagent Price",
			"analyzer_landed_cost": 5000,
			"contract_years": 2,
			"profit_margin_pct": 20,
			"customer": self.customer.name,
			"reagent_lines": [
				{
					"item_code": self.reagent.item_code,
					"test_parameter": self.param.name,
					"monthly_test_volume": 50,
					"cogs_per_pack": 50,
					"tests_per_pack": 100,
				}
			],
		}).insert()
		ws.submit()
		self.worksheet = ws

	def tearDown(self):
		frappe.db.rollback()

	def _make_contract(self, **overrides):
		data = {
			"doctype": "Instrument Placement Contract",
			"contract_title": "_TST Contract",
			"contract_type": "RRA",
			"customer": self.customer.name,
			"customer_site": self.test_site.name,
			"asset": self.test_asset.name,
			"analyzer_pid": self.analyzer.item_code,
			"analyzer_description": "Test Analyzer",
			"pricing_worksheet": self.worksheet.name,
			"start_date": "2026-01-01",
			"end_date": "2027-12-31",
			"contract_reagent_lines": [
				{
					"item_code": self.reagent.item_code,
					"test_parameter": self.param.name,
					"contract_price": 150,
					"standard_price": 50,
					"monthly_test_volume": 100,
				}
			],
		}
		data.update(overrides)
		doc = frappe.get_doc(data).insert()
		return doc

	def test_validate_reagent_restriction(self):
		invalid_item = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Invalid Reagent", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		with self.assertRaises(frappe.ValidationError):
			self._make_contract(contract_reagent_lines=[
				{"item_code": invalid_item.item_code, "contract_price": 100},
			])

	def test_duration_computed(self):
		doc = self._make_contract()
		self.assertEqual(doc.contract_duration_months, 24)

	def test_submit_sets_approval_fields(self):
		doc = self._make_contract()
		doc.submit()
		self.assertEqual(doc.approved_by, frappe.session.user)
		self.assertIsNotNone(doc.approval_date)

	def test_submit_sets_active(self):
		doc = self._make_contract()
		doc.submit()
		self.assertEqual(doc.contract_status, "Active")

	def test_cancel_requires_no_deployment(self):
		doc = self._make_contract()
		doc.submit()
		doc.cancel()
		self.assertEqual(doc.docstatus, 2)
