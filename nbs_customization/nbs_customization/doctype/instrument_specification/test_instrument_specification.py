# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestInstrumentSpecification(FrappeTestCase):
	def setUp(self):
		self.test_item = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test Analyzer for Spec Validation", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		self.test_reagent = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test Reagent for Spec Validation", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": self.test_reagent.item_code,
				"reagent_role": "Test Reagent",
				"default_tests_per_pack": 100,
				"default_cogs_per_pack": 50,
			}
		).insert(ignore_if_duplicate=True)

		self.test_param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_Test Param for Spec Valid", "parameter_code": "TVAL"}
		).insert(ignore_if_duplicate=True)

	def tearDown(self):
		frappe.db.rollback()

	def test_duplicate_test_parameter_blocked(self):
		doc = frappe.get_doc(
			{
				"doctype": "Instrument Specification",
				"item": self.test_item.item_code,
				"supported_test_methods": [
					{"test_parameter": self.test_param.name, "required_reagent": self.test_reagent.item_code},
					{"test_parameter": self.test_param.name, "required_reagent": self.test_reagent.item_code},
				],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_reagent_role_mismatch_blocked(self):
		consumable = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test Consumable for Spec", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": consumable.item_code,
				"reagent_role": "Non-Test Consumable",
			}
		).insert(ignore_if_duplicate=True)

		doc = frappe.get_doc(
			{
				"doctype": "Instrument Specification",
				"item": self.test_item.item_code,
				"supported_test_methods": [
					{"test_parameter": self.test_param.name, "required_reagent": consumable.item_code},
				],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_pass_with_valid_reagent(self):
		doc = frappe.get_doc(
			{
				"doctype": "Instrument Specification",
				"item": self.test_item.item_code,
				"supported_test_methods": [
					{"test_parameter": self.test_param.name, "required_reagent": self.test_reagent.item_code},
				],
			}
		)
		doc.insert()
		self.assertTrue(doc.name)
