# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from nbs_customization.utils.placement.analyzer_menu import resolve_cost_basis
from nbs_customization.utils.placement.dates import validate_not_future
from nbs_customization.utils.placement.pricing_engine import declared_packs
from nbs_customization.utils.pricing import get_current_selling_price


class TestPricingEngine(FrappeTestCase):
	def test_declared_packs(self):
		self.assertEqual(declared_packs(100, 12, 100), 12)
		self.assertEqual(declared_packs(102, 36, 100), 37)


class TestProfileCostBasis(FrappeTestCase):
	def setUp(self):
		self.prefix = f"CB{frappe.generate_hash(length=5)}"
		self.analyzer = _item(f"{self.prefix}-AN")
		self.calibrator = _item(f"{self.prefix}-CAL")
		self.part = _item(f"{self.prefix}-PART")
		frappe.get_doc(
			{
				"doctype": "Analyzer Profile",
				"analyzer_item": self.analyzer,
				"consumables": [
					{
						"item": self.calibrator,
						"role": "Calibrator",
						"consumption_basis": "Per Month",
						"calibration_frequency_days": 30,
						"qty_per_event": 1,
					}
				],
				"maintenance": [{"item": self.part, "qty": 2, "month_no": 6, "action": "Replace"}],
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def test_calibration_and_maintenance_over_term(self):
		rows = resolve_cost_basis(self.analyzer, 12, 20)
		by_source = {row["source_type"]: row for row in rows}
		self.assertAlmostEqual(by_source["Calibration Material"]["quantity_over_term"], 13)
		self.assertAlmostEqual(by_source["Maintenance Part"]["quantity_over_term"], 2)


def _item(code):
	return frappe.get_doc({"doctype": "Item", "item_code": code, "item_group": "Products"}).insert().name


class TestCostBasisOptions(FrappeTestCase):
	def setUp(self):
		self.prefix = f"CB2{frappe.generate_hash(length=5)}"
		self.analyzer = _item(f"{self.prefix}-AN")
		self.day_item = _item(f"{self.prefix}-DAY")
		self.test_item = _item(f"{self.prefix}-TEST")
		self.part = _item(f"{self.prefix}-PART")
		for code, rate in (
			(self.day_item, 100),
			(self.test_item, 200),
		):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": code,
					"price_list": "Standard Selling",
					"price_list_rate": rate,
					"selling": 1,
					"valid_from": "2025-01-01",
				}
			).insert()
		frappe.get_doc(
			{
				"doctype": "Analyzer Profile",
				"analyzer_item": self.analyzer,
				"consumables": [
					{
						"item": self.day_item,
						"role": "Wash",
						"consumption_basis": "Per Day",
						"qty": 1,
					},
					{
						"item": self.test_item,
						"role": "System Solution",
						"consumption_basis": "Per Test",
						"qty": 2,
					},
				],
				"maintenance": [{"item": self.part, "qty": 1, "month_no": 12, "action": "Replace"}],
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def test_per_day_per_test_and_scheduled_maintenance(self):
		rows = resolve_cost_basis(
			self.analyzer,
			6,
			20,
			on_date="2025-06-01",
			monthly_test_volume=100,
		)
		by_item = {row["item_code"]: row for row in rows}
		self.assertEqual(by_item[self.day_item]["quantity_over_term"], 120)
		self.assertEqual(by_item[self.test_item]["quantity_over_term"], 1200)
		self.assertEqual(by_item[self.day_item]["standard_selling_price_per_unit"], 100)
		self.assertNotIn(self.part, by_item)

		rows = resolve_cost_basis(self.analyzer, 18, 20, monthly_test_volume=100)
		by_item = {row["item_code"]: row for row in rows}
		self.assertEqual(by_item[self.part]["quantity_over_term"], 1)

		rows = resolve_cost_basis(self.analyzer, 24, 20, monthly_test_volume=100)
		by_item = {row["item_code"]: row for row in rows}
		self.assertEqual(by_item[self.part]["quantity_over_term"], 2)


class TestTestParameterQuery(FrappeTestCase):
	def setUp(self):
		self.code = f"TSTQ-{frappe.generate_hash(length=5)}"
		frappe.get_doc(
			{
				"doctype": "Test Parameter",
				"parameter_name": "Query Albumin",
				"parameter_code": self.code,
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def test_returns_code_and_name(self):
		from nbs_customization.utils.placement.spec_lines import get_test_parameters

		rows = get_test_parameters("Test Parameter", self.code, "name", 0, 20, {})
		self.assertEqual(rows, [[self.code, f"{self.code} — Query Albumin"]])

	def test_searches_by_parameter_name(self):
		from nbs_customization.utils.placement.spec_lines import get_test_parameters

		rows = get_test_parameters("Test Parameter", "Query Albumin", "name", 0, 20, {})
		self.assertIn(self.code, [row[0] for row in rows])

	def test_respects_page_length(self):
		from nbs_customization.utils.placement.spec_lines import get_test_parameters

		rows = get_test_parameters("Test Parameter", "Query Albumin", "name", 0, 1, {})
		self.assertEqual(len(rows), 1)


class TestAnalyzerSellingPriceLookup(FrappeTestCase):
	def setUp(self):
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"TST-ASP-{frappe.generate_hash(length=5)}",
				"item_group": "Products",
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def _price(self, rate, valid_from=None, valid_upto=None):
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": self.item.name,
				"price_list": "Standard Selling",
				"price_list_rate": rate,
				"selling": 1,
				"valid_from": valid_from or today(),
				"valid_upto": valid_upto,
			}
		).insert()

	def test_returns_active_standard_selling_price(self):
		from nbs_customization.utils.placement.spec_lines import get_analyzer_standard_selling_price

		self._price(123.45)
		self.assertEqual(get_analyzer_standard_selling_price(self.item.name), {"rate": 123.45})

	def test_returns_zero_without_price(self):
		from nbs_customization.utils.placement.spec_lines import get_analyzer_standard_selling_price

		self.assertEqual(get_analyzer_standard_selling_price(self.item.name), {"rate": 0})

	def test_ignores_expired_price(self):
		from nbs_customization.utils.placement.spec_lines import get_analyzer_standard_selling_price

		self._price(123.45, valid_from=add_days(today(), -10), valid_upto=add_days(today(), -1))
		self.assertEqual(get_analyzer_standard_selling_price(self.item.name), {"rate": 0})

	def test_requires_item_read_permission(self):
		from nbs_customization.utils.placement.spec_lines import get_analyzer_standard_selling_price

		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				get_analyzer_standard_selling_price(self.item.name)


class TestPricingTerms(FrappeTestCase):
	def test_multi_component_test_revenue_counted_once(self):
		from nbs_customization.utils.placement.pricing_terms import test_revenue

		lines = [
			frappe._dict(test_parameter="T", monthly_test_volume=100, agreed_test_price=600),
			frappe._dict(test_parameter="T", monthly_test_volume=100, agreed_test_price=600),
		]
		self.assertEqual(test_revenue(lines, 12, "agreed_test_price"), 720000)


class TestPlacementDateRules(FrappeTestCase):
	def test_future_date_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			validate_not_future(add_days(today(), 1), "Posting Date")

	def test_past_date_allowed(self):
		validate_not_future(add_days(today(), -1), "Posting Date")


class TestHistoricalSellingPrice(FrappeTestCase):
	def setUp(self):
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"TST-HIST-{frappe.generate_hash(length=5)}",
				"item_group": "Products",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": self.item.name,
				"price_list": "Standard Selling",
				"price_list_rate": 100,
				"selling": 1,
				"valid_from": "2025-01-01",
				"valid_upto": "2025-12-31",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": self.item.name,
				"price_list": "Standard Selling",
				"price_list_rate": 200,
				"selling": 1,
				"valid_from": "2026-01-01",
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def test_uses_price_valid_on_posting_date(self):
		self.assertEqual(get_current_selling_price(self.item.name, "2025-06-01"), 100)
		self.assertEqual(get_current_selling_price(self.item.name, "2026-06-01"), 200)
