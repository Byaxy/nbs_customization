# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.utils.placement.valid_items import (
	get_reagent_items_for_analyzer,
	validate_items_belong_to_analyzer,
)


class TestValidItems(FrappeTestCase):
	def setUp(self):
		self.analyzer = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Analyzer Valid Items", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

		self.reagent_a = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Reagent A", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		self.reagent_b = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Reagent B", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

		self.cleaning = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Cleaning Soln", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

		for code, role in [(self.reagent_a.item_code, "Test Reagent"), (self.reagent_b.item_code, "Test Reagent")]:
			frappe.get_doc(
				{
					"doctype": "Reagent Specification",
					"item": code,
					"reagent_role": role,
					"default_tests_per_pack": 100,
					"default_cogs_per_pack": 50,
				}
			).insert(ignore_if_duplicate=True)

		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": self.cleaning.item_code,
				"reagent_role": "Non-Test Consumable",
			}
		).insert(ignore_if_duplicate=True)

		self.param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST Param Valid Items", "parameter_code": "TVAL"}
		).insert(ignore_if_duplicate=True)

		frappe.get_doc(
			{
				"doctype": "Instrument Specification",
				"item": self.analyzer.item_code,
				"supported_test_methods": [
					{"test_parameter": self.param.name, "required_reagent": self.reagent_a.item_code},
					{"test_parameter": self.param.name, "required_reagent": self.reagent_b.item_code},
				],
				"required_consumables": [
					{"consumable_item": self.cleaning.item_code, "consumption_qty": 1, "consumption_frequency": "Per Month"},
				],
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def test_returns_all_valid_items(self):
		items = get_reagent_items_for_analyzer(self.analyzer.item_code)
		codes = {i["item_code"] for i in items}
		self.assertIn(self.reagent_a.item_code, codes)
		self.assertIn(self.reagent_b.item_code, codes)
		self.assertIn(self.cleaning.item_code, codes)

	def test_rejects_unlisted_item(self):
		unlisted = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Unlisted Reagent", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

		result = validate_items_belong_to_analyzer(
			self.analyzer.item_code, [unlisted.item_code], throw=False
		)
		self.assertFalse(result)

	def test_raises_on_unlisted_item(self):
		unlisted = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Raise Reagent", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

		with self.assertRaises(frappe.ValidationError):
			validate_items_belong_to_analyzer(
				self.analyzer.item_code, [unlisted.item_code], throw=True
			)

	def test_empty_when_no_spec(self):
		items = get_reagent_items_for_analyzer("Non Existent Item")
		self.assertEqual(items, [])
