# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestAnalyzerProfileIntegrity(IntegrationTestCase):
	def _item(self, suffix):
		return frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"_TST-AP-{suffix}-{frappe.generate_hash(length=5)}",
				"item_group": "Products",
			}
		).insert()

	def test_rejects_item_with_reagent_specification(self):
		item = self._item("REAGENT")
		frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": item.name,
				"reagent_role": "Test Reagent",
			}
		).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Analyzer Profile", "analyzer_item": item.name}).insert()

	def test_blocks_changing_analyzer_item(self):
		first = self._item("FIRST")
		second = self._item("SECOND")
		profile = frappe.get_doc({"doctype": "Analyzer Profile", "analyzer_item": first.name}).insert()
		profile.analyzer_item = second.name
		with self.assertRaises(frappe.ValidationError):
			profile.save()
