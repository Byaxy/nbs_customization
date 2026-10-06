# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from nbs_customization.nbs_customization.doctype.instrument_pricing_worksheet.instrument_pricing_worksheet import (
	make_instrument_placement_contract,
)
from nbs_customization.utils.placement import spec_lines, valid_items
from nbs_customization.utils.placement.valid_items import _restrict_items_to_panel


class TestRRAWorksheet(FrappeTestCase):
	"""Chemistry analyzer RRA — must match §1.5 example."""

	def setUp(self):
		self.analyzer = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Chem Analyzer RRA", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

		self.reagent = self._make_reagent("ALB", 23.10, 102)
		self._setup_spec()

		self.customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "_TST RRA Customer", "customer_type": "Company"}
		).insert(ignore_if_duplicate=True)

		self.param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST RRA Param", "parameter_code": "RRA"}
		).insert(ignore_if_duplicate=True)

		self.ws = frappe.get_doc(
			{
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
			}
		).insert()

	def _setup_spec(self):
		param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST RRA Param", "parameter_code": "RRA"}
		).insert(ignore_if_duplicate=True)
		at = frappe.get_doc({"doctype": "Analyzer Type", "title": "_TST Chemistry"}).insert(
			ignore_if_duplicate=True
		)
		frappe.get_doc(
			{
				"doctype": "Instrument Specification",
				"item": self.analyzer.item_code,
				"analyzer_type": at.name,
				"supported_test_methods": [
					{
						"test_parameter": param.name,
						"required_reagent": self.reagent.item_code,
					}
				],
			}
		).insert(ignore_if_duplicate=True)

	def _make_reagent(self, name, cogs, volume):
		item = frappe.get_doc(
			{"doctype": "Item", "item_code": f"_TST {name}", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": item.item_code,
				"reagent_role": "Test Reagent",
				"default_cogs_per_pack": cogs,
				"default_tests_per_pack": 100,
			}
		).insert(ignore_if_duplicate=True)
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
		self.asset_category = frappe.get_doc(
			{
				"doctype": "Asset Category",
				"asset_category_name": "_TST Apply Asset Cat",
				"depreciation_method": "Straight Line",
				"total_number_of_depreciations": 1,
				"frequency_of_depreciation": 12,
				"accounts": [
					{
						"company_name": self.company,
						"fixed_asset_account": "Capital Equipment - NBS",
					}
				],
			}
		).insert(ignore_if_duplicate=True)

		self.analyzer = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_TST Apply Analyzer",
				"item_group": "Products",
				"is_stock_item": 1,
				"description": "Test Analyzer Description",
			}
		).insert(ignore_if_duplicate=True)

		self.capital_item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_TST Apply Capital",
				"item_group": "Products",
				"is_fixed_asset": 1,
				"is_stock_item": 0,
				"asset_category": self.asset_category.name,
			}
		).insert(ignore_if_duplicate=True)

		at = frappe.get_doc({"doctype": "Analyzer Type", "title": "_TST Apply Chem"}).insert(
			ignore_if_duplicate=True
		)

		param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST Apply Param", "parameter_code": "APLY"}
		).insert(ignore_if_duplicate=True)

		self.reagent = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Apply Reagent", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": self.reagent.item_code,
				"reagent_role": "Test Reagent",
				"default_cogs_per_pack": 50,
				"default_tests_per_pack": 100,
			}
		).insert(ignore_if_duplicate=True)

		frappe.get_doc(
			{
				"doctype": "Instrument Specification",
				"item": self.analyzer.item_code,
				"analyzer_type": at.name,
				"supported_test_methods": [
					{
						"test_parameter": param.name,
						"required_reagent": self.reagent.item_code,
					}
				],
			}
		).insert(ignore_if_duplicate=True)

		self.customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "_TST Apply Customer", "customer_type": "Company"}
		).insert(ignore_if_duplicate=True)

		ws = frappe.get_doc(
			{
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
			}
		).insert()

		ws.submit()
		self.ws = ws

	def tearDown(self):
		frappe.db.rollback()

	def _setup_asset_and_address(self):
		site = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "_TST Apply Site",
				"address_type": "Office",
				"address_line1": "123 Test St",
				"city": "Test City",
			}
		).insert(ignore_if_duplicate=True)
		asset = frappe.get_doc(
			{
				"doctype": "Asset",
				"asset_name": "_TST Apply Asset",
				"item_code": self.capital_item.item_code,
				"company": self.company,
				"gross_purchase_amount": 5000,
				"net_purchase_amount": 5000,
				"asset_category": self.asset_category.name,
				"location": "Block 1",
				"purchase_date": frappe.utils.today(),
				"custom_serial_no": "APLY-001",
				"custom_instrument_specification": self.analyzer.item_code,
			}
		).insert(ignore_if_duplicate=True)
		return asset.name, site.name

	def _make_contract(self, asset=None, site=None):
		frappe.flags.args = {"asset": asset or "", "customer_site": site}
		try:
			contract = make_instrument_placement_contract(self.ws.name)
		finally:
			frappe.flags.args = {}
		contract.insert()
		return contract

	def test_mapped_doc_is_unsaved(self):
		asset, site = self._setup_asset_and_address()
		frappe.flags.args = {"asset": asset, "customer_site": site}
		try:
			mapped = make_instrument_placement_contract(self.ws.name)
		finally:
			frappe.flags.args = {}
		self.assertEqual(mapped.docstatus, 0)
		self.assertFalse(frappe.db.exists("Instrument Placement Contract", mapped.name))
		self.assertEqual(mapped.contract_type, "RRA")
		self.assertEqual(mapped.customer, self.customer.name)
		self.assertEqual(mapped.asset, asset)
		self.assertEqual(mapped.pricing_worksheet, self.ws.name)
		self.assertGreater(len(mapped.contract_reagent_lines), 0)
		self.assertEqual(mapped.total_recovery_target, self.ws.final_revenue_target)

	def test_contract_created(self):
		asset, site = self._setup_asset_and_address()
		contract = self._make_contract(asset, site)
		self.assertEqual(contract.contract_type, "RRA")
		self.assertEqual(contract.customer, self.customer.name)
		self.assertEqual(contract.total_recovery_target, self.ws.final_revenue_target)

	def test_contract_lines_mapped(self):
		asset, site = self._setup_asset_and_address()
		contract = self._make_contract(asset, site)
		self.assertGreater(len(contract.contract_reagent_lines), 0)
		cl = contract.contract_reagent_lines[0]
		self.assertEqual(cl.item_code, self.reagent.item_code)
		self.assertEqual(cl.test_parameter, "APLY")
		self.assertEqual(cl.standard_price, 50)
		self.assertEqual(cl.contract_price, self.ws.reagent_lines[0].selling_price_per_pack)
		# Amendments gate the pack-size lookup on this field; it must mirror
		# the worksheet pack cost or monthly charges inflate (divisor falls to 1).
		self.assertEqual(cl.cogs_per_unit, self.ws.reagent_lines[0].cogs_per_pack)

	def test_price_list_created_on_submit(self):
		asset, site = self._setup_asset_and_address()
		contract = self._make_contract(asset, site)
		self.assertFalse(contract.contract_price_list)
		contract.submit()
		contract.reload()
		self.assertTrue(contract.contract_price_list)

		items = frappe.db.get_all(
			"Item Price",
			filters={
				"price_list": contract.contract_price_list,
			},
		)
		self.assertGreater(len(items), 0)

	def test_worksheet_status_updated(self):
		asset, site = self._setup_asset_and_address()
		contract = self._make_contract(asset, site)
		contract.submit()
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
		contract = self._make_contract(asset, site)
		contract.submit()
		self.ws.reload()
		with self.assertRaises(frappe.ValidationError):
			self.ws.cancel()

	def test_asset_for_other_analyzer_blocked(self):
		other_analyzer = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Apply Analyzer 2", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc(
			{
				"doctype": "Instrument Specification",
				"item": other_analyzer.item_code,
				"analyzer_type": frappe.db.get_value(
					"Instrument Specification", {"item": self.analyzer.item_code}, "analyzer_type"
				),
				"supported_test_methods": [],
			}
		).insert(ignore_if_duplicate=True)
		asset, site = self._setup_asset_and_address()
		frappe.db.set_value("Asset", asset, "custom_instrument_specification", other_analyzer.item_code)
		with self.assertRaises(frappe.ValidationError):
			self._make_contract(asset, site)


class TestWorksheetValidationFixes(FrappeTestCase):
	"""Regression tests for PR #2 review findings (interest, mapping, panel filter)."""

	def setUp(self):
		self.analyzer = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Fix Analyzer", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		self.r1 = self._make_reagent("_TST Fix Reagent 1")
		self.r2 = self._make_reagent("_TST Fix Reagent 2")
		self.p1 = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST Fix Param 1", "parameter_code": "FX1"}
		).insert(ignore_if_duplicate=True)
		self.p2 = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST Fix Param 2", "parameter_code": "FX2"}
		).insert(ignore_if_duplicate=True)
		at = frappe.get_doc({"doctype": "Analyzer Type", "title": "_TST Fix Chem"}).insert(
			ignore_if_duplicate=True
		)
		frappe.get_doc(
			{
				"doctype": "Instrument Specification",
				"item": self.analyzer.item_code,
				"analyzer_type": at.name,
				"supported_test_methods": [
					{"test_parameter": self.p1.name, "required_reagent": self.r1.item_code},
					{"test_parameter": self.p2.name, "required_reagent": self.r2.item_code},
				],
			}
		).insert(ignore_if_duplicate=True)
		self.customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "_TST Fix Customer", "customer_type": "Company"}
		).insert(ignore_if_duplicate=True)

	def _make_reagent(self, name):
		item = frappe.get_doc({"doctype": "Item", "item_code": name, "item_group": "Products"}).insert(
			ignore_if_duplicate=True
		)
		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": item.item_code,
				"reagent_role": "Test Reagent",
				"default_cogs_per_pack": 10,
				"default_tests_per_pack": 100,
			}
		).insert(ignore_if_duplicate=True)
		return item

	def _make_ws(self, contract_type, rate, item_code, test_parameter):
		return frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": self.analyzer.item_code,
				"contract_type": contract_type,
				"calculation_output_type": "Markup Factor on Reagent Price",
				"customer": self.customer.name,
				"analyzer_landed_cost": 8000,
				"contract_years": 3,
				"annual_interest_rate": rate,
				"annual_maintenance_cost_rate": 10,
				"profit_margin_pct": 0,
				"reagent_lines": [
					{
						"item_code": item_code,
						"test_parameter": test_parameter,
						"monthly_test_volume": 100,
						"cogs_per_pack": 10,
						"tests_per_pack": 100,
					}
				],
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def test_non_rlo_interest_cleared_and_ignored(self):
		ws = self._make_ws("RRA", 5, self.r1.item_code, self.p1.name)
		ws.reload()
		self.assertEqual(ws.annual_interest_rate, 0)
		# landed 8000 + maintenance 2400, no interest
		self.assertAlmostEqual(ws.fixed_cost_to_recover, 10400)

	def test_rlo_interest_applied(self):
		ws = self._make_ws("RLO", 10, self.r1.item_code, self.p1.name)
		ws.reload()
		self.assertEqual(ws.annual_interest_rate, 10)
		# 8000 * (1 + 0.10 * 3) + 2400
		self.assertAlmostEqual(ws.fixed_cost_to_recover, 12800)

	def test_mismatched_reagent_throws(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_ws("RRA", 0, self.r2.item_code, self.p1.name)

	def test_panel_filter_keeps_items_without_spec(self):
		panel_at = frappe.get_doc({"doctype": "Analyzer Type", "title": "_TST Fix Panel AT"}).insert(
			ignore_if_duplicate=True
		)
		panel_a = frappe.get_doc(
			{
				"doctype": "Test Panel Group",
				"panel_name": "_TST Panel A",
				"panel_code": "FXPA",
				"analyzer_type": panel_at.name,
			}
		).insert(ignore_if_duplicate=True)
		panel_b = frappe.get_doc(
			{
				"doctype": "Test Panel Group",
				"panel_name": "_TST Panel B",
				"panel_code": "FXPB",
				"analyzer_type": panel_at.name,
			}
		).insert(ignore_if_duplicate=True)
		other = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Fix Other Panel", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": other.item_code,
				"reagent_role": "Test Reagent",
				"test_panel_group": panel_b.name,
			}
		).insert(ignore_if_duplicate=True)
		no_spec = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Fix No Spec", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		kept = _restrict_items_to_panel({other.item_code, no_spec.item_code}, panel_a.name)
		self.assertIn(no_spec.item_code, kept)
		self.assertNotIn(other.item_code, kept)


class TestSpecLookupPermissions(FrappeTestCase):
	"""Analyzer-scoped lookups must deny callers without Item read permission."""

	def tearDown(self):
		frappe.db.rollback()

	def _assert_denied(self, fn, *args, **kwargs):
		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				fn(*args, **kwargs)

	def test_cost_endpoints_require_item_read(self):
		self._assert_denied(spec_lines.get_spec_test_method_details, "_TST X", "_TST P")
		self._assert_denied(spec_lines.get_spec_consumable_details, "_TST X", "_TST C")
		self._assert_denied(spec_lines.get_analyzer_landed_cost, "_TST X")

	def test_search_endpoints_require_item_read(self):
		filters = {"analyzer_item": "_TST X"}
		self._assert_denied(spec_lines.get_spec_test_parameters, "Item", "", "name", 0, 20, filters)
		self._assert_denied(spec_lines.get_spec_consumables, "Item", "", "name", 0, 20, filters)
		self._assert_denied(valid_items.get_valid_reagent_items, "Item", "", "name", 0, 20, filters)

	def test_empty_analyzer_still_returns_empty(self):
		self.assertEqual(spec_lines.get_spec_test_method_details("", "_TST P"), {})
		self.assertEqual(spec_lines.get_spec_consumable_details("", "_TST C"), {})
		self.assertEqual(spec_lines.get_analyzer_landed_cost(""), {"rate": 0})
		self.assertEqual(spec_lines.get_spec_test_parameters("Item", "", "name", 0, 20, {}), [])
		self.assertEqual(spec_lines.get_spec_consumables("Item", "", "name", 0, 20, {}), [])
		self.assertEqual(valid_items.get_valid_reagent_items("Item", "", "name", 0, 20, {}), [])
