# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from nbs_customization.nbs_customization.doctype.instrument_pricing_worksheet.instrument_pricing_worksheet import (
	make_instrument_placement_contract,
)


class TestWorksheetPricing(FrappeTestCase):
	def setUp(self):
		self.prefix = f"P2{frappe.generate_hash(length=6)}"
		self.analyzer = frappe.get_doc(
			{"doctype": "Item", "item_code": f"{self.prefix}-AN", "item_group": "Products"}
		).insert()
		self.reagent = frappe.get_doc(
			{"doctype": "Item", "item_code": f"{self.prefix}-RG", "item_group": "Products"}
		).insert()
		self.consumable = frappe.get_doc(
			{"doctype": "Item", "item_code": f"{self.prefix}-CN", "item_group": "Products"}
		).insert()
		for item in (self.consumable,):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": item.name,
					"price_list": "Standard Selling",
					"selling": 1,
					"price_list_rate": 1000,
				}
			).insert(ignore_permissions=True)
		self.param = frappe.get_doc(
			{
				"doctype": "Test Parameter",
				"parameter_name": "P2 Param",
				"parameter_code": f"{self.prefix}-P",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Analyzer Profile",
				"analyzer_item": self.analyzer.name,
				"reagents": [
					{
						"test_parameter": self.param.name,
						"reagent_item": self.reagent.name,
						"component_role": "Single",
						"is_default": 1,
					}
				],
				"consumables": [
					{"item": self.consumable.name, "role": "Wash", "consumption_basis": "Per Month", "qty": 1}
				],
			}
		).insert()
		self.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"{self.prefix} Customer",
				"customer_type": "Company",
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def _worksheet(self, **overrides):
		values = {
			"doctype": "Instrument Pricing Worksheet",
			"analyzer_pid": self.analyzer.name,
			"contract_type": "RRA",
			"calculation_output_type": "Markup Factor on Reagent Price",
			"customer": self.customer.name,
			"term_months": 60,
			"analyzer_standard_selling_price": 150000,
			"analyzer_landed_cost": 100000,
			"annual_service_maintenance_rate_pct": 10,
			"profit_margin_pct": 25,
			"reagent_lines": [
				{
					"item_code": self.reagent.name,
					"test_parameter": self.param.name,
					"component_role": "Single",
					"monthly_test_volume": 100,
					"gross_tests_per_pack": 500,
					"tests_per_pack": 500,
					"standard_selling_price_per_pack": 50000,
					"cogs_per_pack": 10000,
				}
			],
		}
		values.update(overrides)
		return frappe.get_doc(values).insert()

	def test_service_value_uses_analyzer_standard_selling(self):
		ws = self._worksheet()
		self.assertEqual(ws.total_maintenance_cost, 75000)
		self.assertEqual(ws.total_test_reagent_value, 600000)
		self.assertEqual(ws.standard_sale_base, 825000)
		self.assertEqual(ws.final_revenue_target, 1031250)
		self.assertEqual(ws.benchmark_status, "At or Above Outright")

	def test_manual_consumable_gets_dated_selling_price(self):
		ws = self._worksheet(
			consumable_lines=[
				{
					"item_code": self.consumable.name,
					"consumption_qty": 1,
					"consumption_frequency": "Per Month",
					"cogs_per_unit": 500,
				}
			]
		)
		self.assertEqual(ws.consumable_lines[0].standard_selling_price_per_unit, 1000)

	def test_multi_component_test_counts_tests_once(self):
		second = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"{self.prefix}-LYSE",
				"item_group": "Products",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": second.name,
				"reagent_role": "Test Reagent",
				"default_cogs_per_pack": 10000,
				"default_tests_per_pack": 500,
			}
		).insert()
		profile = frappe.get_doc("Analyzer Profile", {"analyzer_item": self.analyzer.name})
		profile.append(
			"reagents",
			{
				"test_parameter": self.param.name,
				"reagent_item": second.name,
				"component_role": "R2",
				"is_default": 1,
			},
		)
		profile.save(ignore_permissions=True)
		line = {
			"test_parameter": self.param.name,
			"monthly_test_volume": 100,
			"gross_tests_per_pack": 500,
			"standard_selling_price_per_pack": 50000,
			"cogs_per_pack": 10000,
			"price_per_test": 600,
		}
		ws = self._worksheet(
			term_months=12,
			calculation_output_type="Revenue Share Percentage",
			reagent_lines=[
				{**line, "item_code": self.reagent.name, "component_role": "Single"},
				{**line, "item_code": second.name, "component_role": "R2"},
			],
		)
		self.assertEqual(ws.total_monthly_tests, 100)
		self.assertEqual(ws.total_tests_over_term, 1200)
		self.assertEqual(ws.total_gross_test_revenue_over_term, 720000)
		self.assertAlmostEqual(
			ws.required_revenue_share_pct, ws.final_revenue_target / 720000 * 100, places=6
		)

	def test_landed_cost_does_not_change_pricing(self):
		ws = self._worksheet()
		target = ws.final_revenue_target
		ws.analyzer_landed_cost = 200000
		ws.save()
		ws.reload()
		self.assertEqual(ws.final_revenue_target, target)
		self.assertEqual(ws.total_maintenance_cost, 75000)

	def test_analyzer_standard_selling_changes_service(self):
		ws = self._worksheet()
		ws.analyzer_standard_selling_price = 200000
		ws.save()
		ws.reload()
		self.assertEqual(ws.total_maintenance_cost, 100000)
		self.assertEqual(ws.standard_sale_base, 900000)

	def test_term_months_controls_service_and_interest(self):
		ws = self._worksheet(term_months=18, contract_type="RLO", annual_interest_rate=10)
		self.assertEqual(ws.total_maintenance_cost, 22500)
		self.assertEqual(ws.final_revenue_target, ws.standard_sale_base + 22500 + ws.profit_amount)

	def test_markup_denominator_is_standard_selling_value(self):
		ws = self._worksheet()
		self.assertAlmostEqual(ws.markup_factor, 1031250 / 600000, places=4)
		self.assertAlmostEqual(ws.reagent_lines[0].selling_price_per_pack, 50000 * 1031250 / 600000, places=2)

	def test_future_posting_date_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._worksheet(posting_date=add_days(today(), 1))

	def test_volume_and_cost_aggregates(self):
		ws = self._worksheet()
		self.assertEqual(ws.total_monthly_tests, 100)
		self.assertEqual(ws.total_tests_over_term, 6000)
		self.assertEqual(ws.total_reagent_packs, 12)
		self.assertEqual(ws.total_consumable_units, 0)
		self.assertEqual(ws.total_cogs, 120000)
		self.assertEqual(ws.total_interest_cost, 0)

	def test_auto_cost_basis_quantity_refreshes_with_term(self):
		ws = self._worksheet(
			consumable_lines=[
				{
					"item_code": self.consumable.name,
					"source_type": "Analyzer Consumable",
					"source_reference": f"{self.analyzer.name}:Wash",
					"is_auto": 1,
					"quantity_over_term": 999,
					"consumption_frequency": "Computed Over Term",
					"cogs_per_unit": 0,
					"standard_selling_price_per_unit": 0,
				}
			]
		)
		self.assertEqual(ws.consumable_lines[0].quantity_over_term, 60)
		self.assertEqual(ws.total_consumable_units, 60)

	def test_consumables_are_recovered_through_contract(self):
		ws = self._worksheet(
			consumable_lines=[
				{
					"item_code": self.consumable.name,
					"consumption_qty": 1,
					"consumption_frequency": "Per Month",
					"standard_selling_price_per_unit": 1000,
					"cogs_per_unit": 500,
				}
			]
		)
		self.assertEqual(ws.total_consumable_value, 60000)
		self.assertEqual(ws.total_maintenance_cost, 75000)
		self.assertEqual(ws.standard_sale_base, 885000)
		self.assertAlmostEqual(
			ws.markup_factor, ws.final_revenue_target / ws.total_test_reagent_value, places=4
		)

	def test_missing_analyzer_standard_selling_blocks(self):
		with self.assertRaises(frappe.ValidationError):
			self._worksheet(analyzer_standard_selling_price=0)

	def test_contract_snapshot_uses_new_pricing_fields(self):
		ws = self._worksheet()
		ws.submit()
		contract = make_instrument_placement_contract(ws.name)
		self.assertEqual(contract.term_months, 60)
		self.assertEqual(contract.analyzer_standard_selling_price, 150000)
		self.assertEqual(contract.total_maintenance_cost, 75000)
		self.assertEqual(contract.standard_sale_base, 825000)
		self.assertEqual(contract.net_revenue_target, 1031250)
		self.assertEqual(contract.wht_rate_pct, 0)
		self.assertEqual(contract.total_recovery_target, 1031250)
		self.assertEqual(contract.benchmark_status, "At or Above Outright")

	def test_new_worksheet_requires_term_months(self):
		with self.assertRaises(frappe.ValidationError):
			values = {
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": self.analyzer.name,
				"contract_type": "RRA",
				"calculation_output_type": "Markup Factor on Reagent Price",
				"customer": self.customer.name,
				"profit_margin_pct": 0,
				"reagent_lines": [],
			}
			frappe.get_doc(values).insert()

	def test_profit_is_applied_after_interest(self):
		ws = self._worksheet(
			contract_type="RLO", term_months=24, annual_interest_rate=10, profit_margin_pct=25
		)
		base = ws.standard_sale_base
		interest = 150000 * 0.10 * 2
		self.assertEqual(ws.total_cost_base, base + interest)
		self.assertAlmostEqual(ws.profit_amount, (base + interest) * 0.25, places=2)
		self.assertEqual(ws.final_revenue_target, ws.net_revenue_target)

	def test_wht_gross_up_target(self):
		cat = frappe.get_doc(
			{
				"doctype": "Tax Withholding Category",
				"name": "P2 WHT 3%",
				"category_name": "P2 WHT 3%",
				"rates": [{"from_date": "2026-01-01", "to_date": "2026-12-31", "tax_withholding_rate": 3}],
				"accounts": [{"company": "NORTHLAND BIOMEDICAL SOLUTIONS", "account": "WHT-3% - NBS"}],
			}
		).insert()
		self.customer.db_set("tax_withholding_category", cat.name)
		ws = self._worksheet()
		self.assertEqual(ws.wht_rate_pct, 3)
		gross = round(ws.net_revenue_target / 0.97, 2)
		self.assertEqual(ws.final_revenue_target, gross)
		self.assertEqual(ws.wht_amount, round(gross - ws.net_revenue_target, 2))
		self.assertEqual(
			ws.outright_gap_amount, round(ws.net_revenue_target - ws.total_outright_sale_value, 2)
		)

	def test_default_maintenance_rate_is_twelve_percent(self):
		ws = self._worksheet(annual_service_maintenance_rate_pct=0)
		self.assertEqual(ws.total_maintenance_cost, 90000)

	def test_revenue_share_amount_is_stored_separately(self):
		ws = self._worksheet(
			calculation_output_type="Revenue Share Percentage",
			reagent_lines=[
				{
					"item_code": self.reagent.name,
					"test_parameter": self.param.name,
					"component_role": "Single",
					"monthly_test_volume": 100,
					"gross_tests_per_pack": 500,
					"standard_selling_price_per_pack": 50000,
					"cogs_per_pack": 10000,
					"price_per_test": 1000,
				}
			],
		)
		self.assertEqual(ws.required_revenue_share_amount, ws.final_revenue_target)
		self.assertGreater(ws.required_revenue_share_pct, 0)

	def test_gross_tests_per_pack_can_replace_tests_per_pack(self):
		ws = self._worksheet(
			reagent_lines=[
				{
					"item_code": self.reagent.name,
					"test_parameter": self.param.name,
					"component_role": "Single",
					"monthly_test_volume": 100,
					"gross_tests_per_pack": 500,
					"standard_selling_price_per_pack": 50000,
					"cogs_per_pack": 10000,
					"price_per_test": 12.50,
				}
			]
		)
		self.assertEqual(ws.reagent_lines[0].packs_needed, 12)
