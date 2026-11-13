# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAnalyzerType(FrappeTestCase):
	def setUp(self):
		self.item = frappe.get_doc(
			{"doctype": "Item", "item_code": "_TST Analyzer Type Item", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)

	def tearDown(self):
		frappe.db.rollback()

	def test_fixture_types_exist(self):
		self.assertTrue(frappe.db.exists("Analyzer Type", "Chemistry"))
		self.assertTrue(frappe.db.exists("Analyzer Type", "Haematology"))

	def test_profile_accepts_analyzer_type(self):
		profile = frappe.get_doc(
			{
				"doctype": "Analyzer Profile",
				"analyzer_item": self.item.name,
				"analyzer_type": "Chemistry",
			}
		).insert()
		self.assertEqual(profile.analyzer_type, "Chemistry")

	def test_profile_rejects_unknown_analyzer_type(self):
		with self.assertRaises(frappe.LinkValidationError):
			frappe.get_doc(
				{
					"doctype": "Analyzer Profile",
					"analyzer_item": self.item.name,
					"analyzer_type": "Unknown Type",
				}
			).insert()
