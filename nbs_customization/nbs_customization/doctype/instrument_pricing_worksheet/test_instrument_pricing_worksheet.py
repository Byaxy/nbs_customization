# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from nbs_customization.nbs_customization.doctype.instrument_pricing_worksheet.instrument_pricing_worksheet import (
	make_instrument_placement_contract,
)
from nbs_customization.utils.placement import spec_lines, valid_items


class TestRRAWorksheet(FrappeTestCase):
	"""Chemistry analyzer RRA — matches §1.5 example inputs."""

	def setUp(self):
		self.analyzer = _make_item("_TST Chem Analyzer RRA")
		self.reagent = _make_reagent("_TST ALB", cogs=23.10)
		self.param = _make_param("_TST RRA Param", "RRA")
		_make_application(self.analyzer, self.param, self.reagent)
		self.customer = _make_customer("_TST RRA Customer")

		self.ws = frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": self.analyzer,
				"contract_type": "RRA",
				"calculation_output_type": "Markup Factor on Reagent Price",
				"customer": self.customer,
				"analyzer_landed_cost": 8000,
				"analyzer_standard_selling_price": 8000,
				"term_months": 36,
				"annual_service_maintenance_rate_pct": 10,
				"profit_margin_pct": 25,
				"reagent_lines": [
					{
						"item_code": self.reagent,
						"test_parameter": self.param,
						"component_role": "Single",
						"monthly_test_volume": 102,
						"cogs_per_pack": 23.10,
						"tests_per_pack": 100,
						"gross_tests_per_pack": 100,
						"standard_selling_price_per_pack": 23.10,
					}
				],
			}
		).insert()

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
		self.assertIsNotNone(self.ws.calculated_by)
		self.assertIsNotNone(self.ws.calculated_date)

	def test_bg_consumption_monthly_total(self):
		self.ws.operational_days_per_month = 20
		line = self.ws.reagent_lines[0]
		line.bg_consumption_ml_day = 191.71
		line.consumption_ml_per_test = 19
		self.ws.save()
		self.ws.reload()
		line = self.ws.reagent_lines[0]
		self.assertAlmostEqual(line.total_consumption_ml_month, 191.71 * 20 + 19 * 102, places=2)

		line.bg_consumption_ml_month = 3823.4
		self.ws.save()
		self.ws.reload()
		self.assertAlmostEqual(
			self.ws.reagent_lines[0].total_consumption_ml_month,
			3823.4 + 19 * 102,
			places=2,
		)
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
					{"company_name": self.company, "fixed_asset_account": "Capital Equipment - NBS"}
				],
			}
		).insert(ignore_if_duplicate=True)

		self.analyzer = _make_item("_TST Apply Analyzer", description="Test Analyzer Description")
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

		self.param = _make_param("_TST Apply Param", "APLY")
		self.reagent = _make_reagent("_TST Apply Reagent", cogs=50)
		_make_application(self.analyzer, self.param, self.reagent)
		self.customer = _make_customer("_TST Apply Customer")

		self.ws = frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": self.analyzer,
				"contract_type": "RRA",
				"calculation_output_type": "Markup Factor on Reagent Price",
				"analyzer_landed_cost": 5000,
				"analyzer_standard_selling_price": 5000,
				"term_months": 24,
				"profit_margin_pct": 20,
				"customer": self.customer,
				"reagent_lines": [
					{
						"item_code": self.reagent,
						"test_parameter": self.param,
						"component_role": "Single",
						"monthly_test_volume": 50,
						"cogs_per_pack": 50,
						"tests_per_pack": 100,
						"gross_tests_per_pack": 100,
						"standard_selling_price_per_pack": 50,
					}
				],
			}
		).insert()
		self.ws.submit()

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
				"custom_analyzer_profile": self.analyzer,
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
		self.assertEqual(mapped.customer, self.customer)
		self.assertEqual(mapped.asset, asset)
		self.assertEqual(mapped.pricing_worksheet, self.ws.name)
		self.assertGreater(len(mapped.contract_reagent_lines), 0)
		self.assertEqual(mapped.total_recovery_target, self.ws.final_revenue_target)
		self.assertEqual(mapped.company, self.ws.company)
		self.assertEqual(mapped.naming_series, "NBSIPC-.YYYY./.####")

	def test_contract_created(self):
		asset, site = self._setup_asset_and_address()
		contract = self._make_contract(asset, site)
		self.assertEqual(contract.contract_type, "RRA")
		self.assertEqual(contract.customer, self.customer)
		self.assertTrue(contract.name.startswith("NBSIPC-"))
		self.assertEqual(contract.total_recovery_target, self.ws.final_revenue_target)

	def test_contract_lines_mapped(self):
		asset, site = self._setup_asset_and_address()
		contract = self._make_contract(asset, site)
		line = contract.contract_reagent_lines[0]
		self.assertEqual(line.item_code, self.reagent)
		self.assertEqual(line.test_parameter, "APLY")
		self.assertEqual(line.standard_price, 50)
		self.assertEqual(line.contract_price, self.ws.reagent_lines[0].selling_price_per_pack)
		self.assertEqual(line.cogs_per_unit, self.ws.reagent_lines[0].cogs_per_pack)

	def test_price_list_created_on_submit(self):
		asset, site = self._setup_asset_and_address()
		contract = self._make_contract(asset, site)
		self.assertFalse(contract.contract_price_list)
		contract.submit()
		contract.reload()
		self.assertTrue(contract.contract_price_list)
		self.assertTrue(frappe.db.get_all("Item Price", filters={"price_list": contract.contract_price_list}))

	def test_worksheet_status_updated(self):
		asset, site = self._setup_asset_and_address()
		contract = self._make_contract(asset, site)
		contract.submit()
		self.ws.reload()
		self.assertEqual(self.ws.status, "Applied to Contract")
		self.assertTrue(self.ws.linked_contract)

	def test_cancel_rejected_when_linked(self):
		asset, site = self._setup_asset_and_address()
		contract = self._make_contract(asset, site)
		contract.submit()
		self.ws.reload()
		with self.assertRaises(frappe.ValidationError):
			self.ws.cancel()

	def test_asset_for_other_analyzer_blocked(self):
		other_analyzer = _make_item("_TST Apply Analyzer 2")
		frappe.get_doc({"doctype": "Analyzer Profile", "analyzer_item": other_analyzer}).insert(
			ignore_if_duplicate=True
		)
		asset, site = self._setup_asset_and_address()
		frappe.db.set_value("Asset", asset, "custom_analyzer_profile", other_analyzer)
		with self.assertRaises(frappe.ValidationError):
			self._make_contract(asset, site)


class TestWorksheetValidationFixes(FrappeTestCase):
	"""Regression tests for interest, mapping, multi-reagent, and duplicates."""

	def setUp(self):
		self.analyzer = _make_item("_TST Fix Analyzer")
		self.r1 = _make_reagent("_TST Fix Reagent 1", cogs=10)
		self.r2 = _make_reagent("_TST Fix Reagent 2", cogs=10)
		self.p1 = _make_param("_TST Fix Param 1", "FX1")
		self.p2 = _make_param("_TST Fix Param 2", "FX2")
		_make_application(self.analyzer, self.p1, self.r1)
		_make_application(self.analyzer, self.p2, self.r2)
		self.customer = _make_customer("_TST Fix Customer")

	def tearDown(self):
		frappe.db.rollback()

	def _make_ws(self, contract_type, rate, item_code, test_parameter):
		return frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": self.analyzer,
				"contract_type": contract_type,
				"calculation_output_type": "Markup Factor on Reagent Price",
				"customer": self.customer,
				"analyzer_landed_cost": 8000,
				"analyzer_standard_selling_price": 8000,
				"term_months": 36,
				"annual_interest_rate": rate,
				"annual_service_maintenance_rate_pct": 10,
				"profit_margin_pct": 0,
				"reagent_lines": [
					{
						"item_code": item_code,
						"test_parameter": test_parameter,
						"monthly_test_volume": 100,
						"cogs_per_pack": 10,
						"tests_per_pack": 100,
						"gross_tests_per_pack": 100,
						"standard_selling_price_per_pack": 10,
					}
				],
			}
		).insert()

	def test_non_rlo_interest_cleared_and_ignored(self):
		ws = self._make_ws("RRA", 5, self.r1, self.p1)
		ws.reload()
		self.assertEqual(ws.annual_interest_rate, 0)
		self.assertAlmostEqual(ws.fixed_cost_to_recover, 10400)

	def test_rlo_interest_applied(self):
		ws = self._make_ws("RLO", 10, self.r1, self.p1)
		ws.reload()
		self.assertEqual(ws.annual_interest_rate, 10)
		self.assertAlmostEqual(ws.fixed_cost_to_recover, 12800)

	def test_mismatched_reagent_throws(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_ws("RRA", 0, self.r2, self.p1)

	def test_zero_tests_per_pack_rejected(self):
		ws = frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": self.analyzer,
				"contract_type": "RRA",
				"calculation_output_type": "Markup Factor on Reagent Price",
				"customer": self.customer,
				"analyzer_standard_selling_price": 8000,
				"term_months": 36,
				"reagent_lines": [
					{
						"item_code": self.r1,
						"test_parameter": self.p1,
						"monthly_test_volume": 100,
						"cogs_per_pack": 10,
						"tests_per_pack": 0,
						"standard_selling_price_per_pack": 10,
					}
				],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			ws.insert()

	def test_revenue_share_requires_price_per_test(self):
		ws = frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": self.analyzer,
				"contract_type": "CPT",
				"calculation_output_type": "Revenue Share Percentage",
				"customer": self.customer,
				"analyzer_standard_selling_price": 8000,
				"term_months": 36,
				"reagent_lines": [
					{
						"item_code": self.r1,
						"test_parameter": self.p1,
						"monthly_test_volume": 100,
						"cogs_per_pack": 10,
						"tests_per_pack": 100,
						"gross_tests_per_pack": 100,
						"standard_selling_price_per_pack": 10,
					}
				],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			ws.insert()

	def test_duplicate_reagent_lines_rejected(self):
		line = {
			"item_code": self.r1,
			"test_parameter": self.p1,
			"component_role": "Single",
			"monthly_test_volume": 100,
			"cogs_per_pack": 10,
			"tests_per_pack": 100,
			"gross_tests_per_pack": 100,
			"standard_selling_price_per_pack": 10,
		}
		ws = frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": self.analyzer,
				"contract_type": "RRA",
				"calculation_output_type": "Markup Factor on Reagent Price",
				"customer": self.customer,
				"analyzer_standard_selling_price": 8000,
				"term_months": 36,
				"reagent_lines": [dict(line), dict(line)],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			ws.insert()

	def test_multi_reagent_application_accepted(self):
		second = _make_reagent("_TST Fix Lyse", cogs=5, item_role="Lyse")
		profile = frappe.get_doc("Analyzer Profile", {"analyzer_item": self.analyzer})
		profile.append(
			"reagents",
			{"test_parameter": self.p1, "reagent_item": second, "component_role": "Lyse"},
		)
		profile.save(ignore_permissions=True)
		ws = frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": self.analyzer,
				"contract_type": "RRA",
				"calculation_output_type": "Markup Factor on Reagent Price",
				"customer": self.customer,
				"analyzer_landed_cost": 8000,
				"analyzer_standard_selling_price": 8000,
				"term_months": 36,
				"reagent_lines": [
					{
						"item_code": item,
						"test_parameter": self.p1,
						"component_role": role,
						"monthly_test_volume": 100,
						"cogs_per_pack": 10,
						"tests_per_pack": 100,
						"gross_tests_per_pack": 100,
						"standard_selling_price_per_pack": 10,
					}
					for item, role in ((self.r1, "Single"), (second, "Lyse"))
				],
			}
		).insert()
		self.assertEqual(len(ws.reagent_lines), 2)


class TestSpecLookupPermissions(FrappeTestCase):
	"""Analyzer-scoped lookups must deny callers without Item read permission."""

	def tearDown(self):
		frappe.db.rollback()

	def _assert_denied(self, fn, *args, **kwargs):
		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				fn(*args, **kwargs)

	def test_cost_endpoints_require_item_read(self):
		self._assert_denied(spec_lines.get_test_reagent_components, "_TST X", "_TST P")
		self._assert_denied(spec_lines.get_analyzer_consumable_details, "_TST X", "_TST C")
		self._assert_denied(spec_lines.get_analyzer_landed_cost, "_TST X")

	def test_search_endpoints_require_item_read(self):
		filters = {"analyzer_item": "_TST X"}
		self._assert_denied(spec_lines.get_analyzer_test_parameters, "Item", "", "name", 0, 20, filters)
		self._assert_denied(spec_lines.get_analyzer_consumables, "Item", "", "name", 0, 20, filters)
		self._assert_denied(valid_items.get_valid_reagent_items, "Item", "", "name", 0, 20, filters)

	def test_empty_analyzer_still_returns_empty(self):
		self.assertEqual(spec_lines.get_test_reagent_components("", "_TST P"), [])
		self.assertEqual(spec_lines.get_analyzer_consumable_details("", "_TST C"), {})
		self.assertEqual(spec_lines.get_analyzer_landed_cost(""), {"rate": 0})
		self.assertEqual(spec_lines.get_analyzer_test_parameters("Item", "", "name", 0, 20, {}), [])
		self.assertEqual(spec_lines.get_analyzer_consumables("Item", "", "name", 0, 20, {}), [])
		self.assertEqual(valid_items.get_valid_reagent_items("Item", "", "name", 0, 20, {}), [])


def _make_item(code, description=None):
	return (
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_group": "Products",
				"description": description,
			}
		)
		.insert(ignore_if_duplicate=True)
		.name
	)


def _make_param(name, code):
	return (
		frappe.get_doc({"doctype": "Test Parameter", "parameter_name": name, "parameter_code": code})
		.insert(ignore_if_duplicate=True)
		.name
	)


def _make_reagent(code, cogs, item_role="Test Reagent"):
	item = _make_item(code)
	frappe.get_doc(
		{
			"doctype": "Reagent Specification",
			"item": item,
			"reagent_role": "Test Reagent",
			"item_role": item_role,
			"default_cogs_per_pack": cogs,
			"default_tests_per_pack": 100,
		}
	).insert(ignore_if_duplicate=True)
	return item


def _make_customer(name):
	return (
		frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"})
		.insert(ignore_if_duplicate=True)
		.name
	)


def _make_application(analyzer, param, reagent):
	profile_name = frappe.db.get_value("Analyzer Profile", {"analyzer_item": analyzer}, "name")
	profile = (
		frappe.get_doc("Analyzer Profile", profile_name)
		if profile_name
		else frappe.get_doc({"doctype": "Analyzer Profile", "analyzer_item": analyzer}).insert(
			ignore_if_duplicate=True
		)
	)
	if not any(row.test_parameter == param and row.reagent_item == reagent for row in profile.reagents):
		profile.append(
			"reagents",
			{
				"test_parameter": param,
				"reagent_item": reagent,
				"component_role": "Single",
				"is_default": 1,
			},
		)
		profile.save(ignore_permissions=True)
	return profile.name
