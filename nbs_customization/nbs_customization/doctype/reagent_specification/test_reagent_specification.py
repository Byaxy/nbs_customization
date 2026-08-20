# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestReagentSpecification(FrappeTestCase):
	def setUp(self):
		self.reagent_item = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test RSpec Role Item", "item_group": "Products"}
		).insert(ignore_if_duplicate=True)
		self.rs = frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": self.reagent_item.item_code,
				"reagent_role": "Test Reagent",
				"default_tests_per_pack": 100,
				"default_cogs_per_pack": 50,
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback()

	def test_role_change_blocked_when_referenced_by_active_worksheet(self):
		analyzer = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test Analyzer for RSpec", "item_group": "Products"}
		).insert()

		param = frappe.get_doc(
			{"doctype": "Test Parameter", "parameter_name": "_TST RSpec Param", "parameter_code": "RSPC"}
		).insert(ignore_if_duplicate=True)
		frappe.get_doc({
			"doctype": "Instrument Specification",
			"item": analyzer.item_code,
			"supported_test_methods": [
				{"test_parameter": param.name, "required_reagent": self.reagent_item.item_code},
			],
		}).insert()

		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": "_TST RSpec Customer", "customer_type": "Company"
		}).insert(ignore_if_duplicate=True)

		ws = frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": analyzer.item_code,
				"contract_type": "RRA",
				"calculation_output_type": "Markup Factor on Reagent Price",
				"analyzer_landed_cost": 1000,
				"contract_years": 1,
				"customer": customer.name,
				"reagent_lines": [
					{
						"item_code": self.reagent_item.item_code,
						"test_parameter": param.name,
						"monthly_test_volume": 0,
					}
				],
			}
		).insert()
		ws.status = "Approved"
		ws.save()

		self.rs.reagent_role = "Non-Test Consumable"
		self.assertRaises(frappe.ValidationError, self.rs.save)

		ws.delete()

	def test_role_change_allowed_when_no_references(self):
		self.rs.reagent_role = "Non-Test Consumable"
		try:
			self.rs.save()
		except frappe.ValidationError:
			self.fail("Role change should have been allowed with no downstream refs")
