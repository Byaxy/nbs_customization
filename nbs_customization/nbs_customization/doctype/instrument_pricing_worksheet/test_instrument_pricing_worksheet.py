# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestRRAWorksheet(FrappeTestCase):
	"""Chemistry analyzer RRA — must match §1.5 example."""

	def setUp(self):
		self.analyzer = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Chem Analyzer RRA", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

		self.reagent = self._make_reagent("ALB", 23.10, 102)
		self._setup_spec()

		self.customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "_TST RRA Customer", "customer_type": "Company"
		}).insert(ignore_if_duplicate=True)

		self.param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST RRA Param", "parameter_code": "RRA"}
		).insert(ignore_if_duplicate=True)

		self.ws = frappe.get_doc({
			"doctype": "Instrument Pricing Worksheet",
			"analyzer_pid": self.analyzer.item_code,
			"contract_type": "RRA",
			"calculation_output_type": "Markup Factor on Reagent Price",
			"customer": self.customer.name,
			"analyzer_landed_cost": 8000,
			"contract_years": 3,
			"annual_maintenance_cost_rate": 10,
			"profit_margin_pct": 25,
			"reagent_lines": [
				{
					"item_code": self.reagent.item_code,
					"test_parameter": self.param.name,
					"monthly_test_volume": 102,
					"cogs_per_pack": 23.10,
					"tests_per_pack": 100,
				}
			],
		}).insert()

	def _setup_spec(self):
		param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST ALB", "parameter_code": "ALB"}
		).insert(ignore_if_duplicate=True)
		at = frappe.get_doc(
			{"doctype": "Analyzer Type", "title": "_TST Chemistry"}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc({
			"doctype": "Instrument Specification",
			"item": self.analyzer.item_code,
			"analyzer_type": at.name,
			"supported_test_methods": [{
				"test_parameter": param.name,
				"required_reagent": self.reagent.item_code,
			}],
		}).insert(ignore_if_duplicate=True)

	def _make_reagent(self, name, cogs, volume):
		item = frappe.get_doc({
			"doctype": "Item", "item_code": f"_TST {name}", "item_group": "Products"
		}).insert(ignore_if_duplicate=True)
		frappe.get_doc({
			"doctype": "Reagent Specification",
			"item": item.item_code,
			"reagent_role": "Test Reagent",
			"default_cogs_per_pack": cogs,
			"default_tests_per_pack": 100,
		}).insert(ignore_if_duplicate=True)
		return item

	def tearDown(self):
		frappe.db.rollback()

	def test_rra_markup_factor(self):
		self.ws.reload()

		self.assertAlmostEqual(self.ws.analyzer_landed_cost, 8000)
		self.assertEqual(self.ws.total_maintenance_cost, 2400)

		self.assertAlmostEqual(self.ws.total_test_reagent_cogs, 854.70, places=2)
		self.assertAlmostEqual(self.ws.fixed_cost_to_recover, 10400)
		self.assertAlmostEqual(self.ws.total_cost_base, 11254.70, places=2)
		self.assertAlmostEqual(self.ws.profit_amount, 2813.675, places=2)
		self.assertAlmostEqual(self.ws.final_revenue_target, 14068.375, places=2)

		self.assertAlmostEqual(self.ws.markup_factor, 14068.375 / 854.70, places=4)

	def test_draft_status_after_insert(self):
		self.ws.reload()
		self.assertEqual(self.ws.status, "Draft")
		self.assertEqual(self.ws.docstatus, 0)

	def test_auto_calculation_on_save(self):
		self.ws.reload()
		# calculated fields should be set by validate() on insert
		self.assertIsNotNone(self.ws.calculated_by)
		self.assertIsNotNone(self.ws.calculated_date)
		self.assertGreater(self.ws.final_revenue_target, 0)

	def test_submit_sets_approval_fields(self):
		self.ws.reload()
		self.ws.submit()

		self.assertEqual(self.ws.docstatus, 1)
		self.assertEqual(self.ws.status, "Approved")
		self.assertEqual(self.ws.approved_by, frappe.session.user)
		self.assertIsNotNone(self.ws.approval_date)


class TestApplyWorksheet(FrappeTestCase):
	def setUp(self):
		self.company = "Northland Biomedical Solutions"
		self.asset_category = frappe.get_doc({
			"doctype": "Asset Category",
			"asset_category_name": "_TST Apply Asset Cat",
			"depreciation_method": "Straight Line",
			"total_number_of_depreciations": 1,
			"frequency_of_depreciation": 12,
			"accounts": [{
				"company_name": self.company,
				"fixed_asset_account": "Capital Equipment - NBS",
			}],
		}).insert(ignore_if_duplicate=True)

		self.analyzer = frappe.get_doc({
			"doctype": "Item", "item_code": "_TST Apply Analyzer", "item_group": "Products",
			"is_stock_item": 1,
			"description": "Test Analyzer Description",
		}).insert(ignore_if_duplicate=True)

		self.capital_item = frappe.get_doc({
			"doctype": "Item", "item_code": "_TST Apply Capital", "item_group": "Products",
			"is_fixed_asset": 1, "is_stock_item": 0,
			"asset_category": self.asset_category.name,
		}).insert(ignore_if_duplicate=True)

		at = frappe.get_doc(
			{"doctype": "Analyzer Type", "title": "_TST Apply Chem"}
		).insert(ignore_if_duplicate=True)

		param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST Apply Param", "parameter_code": "APLY"}
		).insert(ignore_if_duplicate=True)

		self.reagent = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Apply Reagent", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

		frappe.get_doc({
			"doctype": "Reagent Specification",
			"item": self.reagent.item_code,
			"reagent_role": "Test Reagent",
			"default_cogs_per_pack": 50,
			"default_tests_per_pack": 100,
		}).insert(ignore_if_duplicate=True)

		frappe.get_doc({
			"doctype": "Instrument Specification",
			"item": self.analyzer.item_code,
			"analyzer_type": at.name,
			"supported_test_methods": [{
				"test_parameter": param.name,
				"required_reagent": self.reagent.item_code,
			}],
		}).insert(ignore_if_duplicate=True)

		self.customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "_TST Apply Customer", "customer_type": "Company"
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
					"test_parameter": param.name,
					"monthly_test_volume": 50,
					"cogs_per_pack": 50,
					"tests_per_pack": 100,
				}
			],
		}).insert()

		ws.submit()
		self.ws = ws

	def tearDown(self):
		frappe.db.rollback()

	def _setup_asset_and_address(self):
		site = frappe.get_doc({
			"doctype": "Address", "address_title": "_TST Apply Site", "address_type": "Office",
			"address_line1": "123 Test St", "city": "Test City",
		}).insert(ignore_if_duplicate=True)
		asset = frappe.get_doc({
			"doctype": "Asset", "asset_name": "_TST Apply Asset",
			"item_code": self.capital_item.item_code,
			"company": self.company,
			"gross_purchase_amount": 5000,
			"net_purchase_amount": 5000,
			"asset_category": self.asset_category.name,
			"location": "Block 1",
			"purchase_date": frappe.utils.today(),
			"custom_serial_no": "APLY-001",
		}).insert(ignore_if_duplicate=True)
		return asset.name, site.name

	def test_contract_created(self):
		asset, site = self._setup_asset_and_address()
		contract_name = self.ws.apply_worksheet_to_contract(asset, site)
		contract = frappe.get_doc("Instrument Placement Contract", contract_name)
		self.assertEqual(contract.contract_type, "RRA")
		self.assertEqual(contract.customer, self.customer.name)
		self.assertEqual(contract.total_recovery_target, self.ws.final_revenue_target)

	def test_contract_lines_mapped(self):
		asset, site = self._setup_asset_and_address()
		contract_name = self.ws.apply_worksheet_to_contract(asset, site)
		contract = frappe.get_doc("Instrument Placement Contract", contract_name)
		self.assertGreater(len(contract.contract_reagent_lines), 0)
		cl = contract.contract_reagent_lines[0]
		self.assertEqual(cl.item_code, self.reagent.item_code)

	def test_price_list_created(self):
		asset, site = self._setup_asset_and_address()
		contract_name = self.ws.apply_worksheet_to_contract(asset, site)
		contract = frappe.get_doc("Instrument Placement Contract", contract_name)
		self.assertTrue(contract.contract_price_list)

		items = frappe.db.get_all("Item Price", filters={
			"price_list": contract.contract_price_list,
		})
		self.assertGreater(len(items), 0)

	def test_worksheet_status_updated(self):
		asset, site = self._setup_asset_and_address()
		self.ws.apply_worksheet_to_contract(asset, site)
		self.ws.reload()
		self.assertEqual(self.ws.status, "Applied to Contract")
		self.assertTrue(self.ws.linked_contract)

	def test_submit_sets_approval_fields(self):
		self.assertEqual(self.ws.docstatus, 1)
		self.assertEqual(self.ws.status, "Approved")
		self.assertIsNotNone(self.ws.approved_by)
		self.assertIsNotNone(self.ws.approval_date)

	def test_cancel_rejected_when_linked(self):
		asset, site = self._setup_asset_and_address()
		self.ws.apply_worksheet_to_contract(asset, site)
		self.ws.reload()
		with self.assertRaises(frappe.ValidationError):
			self.ws.cancel()
