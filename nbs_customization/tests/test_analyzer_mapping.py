# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.tests.placement_fixtures import skip_test_record_bootstrap
from nbs_customization.utils.placement.analyzer_menu import (
	clear_analyzer_menu_cache,
	get_analyzer_menu,
	resolve_consumable_requirements,
	resolve_default_application,
	resolve_maintenance,
	resolve_menu,
	resolve_panel,
	resolve_test,
)


class TestAnalyzerMapping(IntegrationTestCase):
	def setUp(self):
		for doctype in (
			"Analyzer Test Application",
			"Analyzer Assay Group",
			"Analyzer Calibration Rule",
			"Analyzer Consumable Requirement",
			"Analyzer Maintenance Part",
			"Test Panel",
			"Test Panel Parameter",
			"Test Parameter",
			"Reagent Specification",
			"Instrument Specification",
		):
			skip_test_record_bootstrap(doctype)

		self.prefix = f"P1{frappe.generate_hash(length=6)}"
		self.analyzer = self._item(f"{self.prefix}-AN")
		self.reagent = self._item(f"{self.prefix}-RG")
		self.consumable = self._item(f"{self.prefix}-CN")
		self.part = self._item(f"{self.prefix}-PT")
		self.param = frappe.get_doc(
			{
				"doctype": "Test Parameter",
				"parameter_name": "Plan 1 Parameter",
				"parameter_code": f"{self.prefix}-PARAM",
				"result_type": "Measured",
			}
		).insert()
		self.panel = frappe.get_doc(
			{
				"doctype": "Test Panel",
				"panel_code": f"{self.prefix}-PANEL",
				"panel_name": "Plan 1 Panel",
				"parameters": [{"test_parameter": self.param.name, "sequence": 1}],
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": self.reagent,
				"reagent_role": "Test Reagent",
				"item_role": "Test Reagent",
				"component_type": "Single",
			}
		).insert()
		self.application = frappe.get_doc(
			{
				"doctype": "Analyzer Test Application",
				"analyzer_item": self.analyzer,
				"test_parameter": self.param.name,
				"application_code": f"{self.prefix}-APP",
				"sample_type": "Serum",
				"is_default": 1,
				"reagents": [
					{
						"reagent_item": self.reagent,
						"component_role": "Single",
						"consumption_basis": "Per Test",
						"qty_per_test": 0.01,
						"efficiency_pct": 100,
					}
				],
			}
		).insert()
		clear_analyzer_menu_cache()

	def _item(self, code):
		return (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_group": "Products",
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			)
			.insert(ignore_if_duplicate=True)
			.name
		)

	def test_resolve_menu_default_and_panel(self):
		menu = resolve_menu(self.analyzer)
		self.assertEqual(len(menu["applications"]), 1)
		self.assertEqual(menu["panels"][0]["name"], self.panel.name)
		self.assertEqual(
			resolve_default_application(self.analyzer, self.param.name, "Serum"),
			self.application.name,
		)
		test = resolve_test(self.analyzer, self.param.name, sample_type="Serum")
		self.assertEqual(test["name"], self.application.name)
		self.assertEqual(len(test["reagents"]), 1)
		rows = resolve_panel(self.analyzer, self.panel.name)
		self.assertEqual(rows[0]["application"]["name"], self.application.name)

	def test_duplicate_default_blocks(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Analyzer Test Application",
					"analyzer_item": self.analyzer,
					"test_parameter": self.param.name,
					"application_code": f"{self.prefix}-APP-2",
					"sample_type": "Serum",
					"is_default": 1,
				}
			).insert()

	def test_cache_invalidates_on_new_application(self):
		get_analyzer_menu(self.analyzer)
		param = frappe.get_doc(
			{
				"doctype": "Test Parameter",
				"parameter_name": "Plan 1 Parameter 2",
				"parameter_code": f"{self.prefix}-PARAM2",
				"result_type": "Measured",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Analyzer Test Application",
				"analyzer_item": self.analyzer,
				"test_parameter": param.name,
				"application_code": f"{self.prefix}-APP-3",
				"sample_type": "Serum",
			}
		).insert()
		self.assertEqual(len(get_analyzer_menu(self.analyzer)["applications"]), 2)

	def test_calculated_parameter_needs_source(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Test Parameter",
					"parameter_name": "Calculated Without Source",
					"parameter_code": f"{self.prefix}-CALC",
					"result_type": "Calculated",
				}
			).insert()

	def test_maintenance_schedule_counts_from_term_months(self):
		part = frappe.get_doc(
			{
				"doctype": "Analyzer Maintenance Part",
				"analyzer_item": self.analyzer,
				"part_item": self.part,
				"qty": 1,
				"schedule": [
					{"month_no": 3, "action": "Replace"},
					{"month_no": 6, "action": "Replace"},
					{"month_no": 9, "action": "Replace"},
					{"month_no": 12, "action": "Replace"},
				],
			}
		).insert()
		self.assertEqual(resolve_maintenance(part, 60), 20)

	def test_consumable_scope_aggregation(self):
		frappe.get_doc(
			{
				"doctype": "Analyzer Consumable Requirement",
				"analyzer_item": self.analyzer,
				"consumable_item": self.consumable,
				"consumable_role": "Wash",
				"scope": "All Assays",
				"consumption_basis": "Per Day",
				"qty": 2,
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Analyzer Consumable Requirement",
				"analyzer_item": self.analyzer,
				"consumable_item": self.consumable,
				"consumable_role": "Wash",
				"scope": "Selected Applications",
				"consumption_basis": "Per Day",
				"qty": 3,
				"applications": [{"application": self.application.name}],
			}
		).insert()
		rows = resolve_consumable_requirements(self.analyzer)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["qty"], 5)

	def test_multi_test_group_needs_two_members(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Analyzer Assay Group",
					"analyzer_item": self.analyzer,
					"group_name": "Single Member Group",
					"run_basis": "Per Sample",
					"tests": [{"test_parameter": self.param.name, "sequence": 1}],
				}
			).insert()

	def test_reagent_role_mismatch_blocks(self):
		diluent = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"{self.prefix}-DIL",
				"item_group": "Products",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": diluent.name,
				"reagent_role": "Test Reagent",
				"item_role": "Diluent",
			}
		).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Analyzer Test Application",
					"analyzer_item": self.analyzer,
					"test_parameter": self.param.name,
					"application_code": f"{self.prefix}-BAD-ROLE",
					"reagents": [
						{
							"reagent_item": diluent.name,
							"component_role": "R1",
							"consumption_basis": "Per Test",
						}
					],
				}
			).insert()
