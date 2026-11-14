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
		frappe.get_doc(
			{
				"doctype": "Analyzer Profile",
				"analyzer_item": analyzer.item_code,
				"reagents": [
					{
						"test_parameter": param.name,
						"reagent_item": self.reagent_item.item_code,
						"component_role": "Single",
					}
				],
			}
		).insert()

		customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": "_TST RSpec Customer", "customer_type": "Company"}
		).insert(ignore_if_duplicate=True)

		ws = frappe.get_doc(
			{
				"doctype": "Instrument Pricing Worksheet",
				"analyzer_pid": analyzer.item_code,
				"contract_type": "RRA",
				"calculation_output_type": "Markup Factor on Reagent Price",
				"analyzer_landed_cost": 1000,
				"analyzer_standard_selling_price": 1000,
				"term_months": 12,
				"customer": customer.name,
				"reagent_lines": [
					{
						"item_code": self.reagent_item.item_code,
						"test_parameter": param.name,
						"component_role": "Single",
						"monthly_test_volume": 100,
						"tests_per_pack": 100,
						"gross_tests_per_pack": 100,
						"standard_selling_price_per_pack": 50,
					}
				],
			}
		).insert()
		# Status is controller-managed (_sync_status forces Draft while docstatus 0).
		ws.db_set("status", "Approved")

		self.rs.reagent_role = "Non-Test Consumable"
		self.assertRaises(frappe.ValidationError, self.rs.save)

		ws.delete()

	def test_role_change_allowed_when_no_references(self):
		self.rs.reagent_role = "Non-Test Consumable"
		try:
			self.rs.save()
		except frappe.ValidationError:
			self.fail("Role change should have been allowed with no downstream refs")

	def test_saving_spec_sets_item_field(self):
		frappe.db.rollback()
		item = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test RSpec Auto Link", "item_group": "Products"}
		).insert()
		spec = frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": item.name,
				"reagent_role": "Test Reagent",
				"default_tests_per_pack": 100,
				"default_cogs_per_pack": 50,
			}
		).insert()
		self.assertEqual(frappe.db.get_value("Item", item.name, "custom_reagent_specification"), spec.name)

	def test_trash_clears_item_field(self):
		frappe.db.rollback()
		item = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test RSpec Trash Link", "item_group": "Products"}
		).insert()
		spec = frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": item.name,
				"reagent_role": "Test Reagent",
				"default_tests_per_pack": 100,
				"default_cogs_per_pack": 50,
			}
		).insert()
		frappe.delete_doc("Reagent Specification", spec.name, force=True)
		self.assertFalse(frappe.db.get_value("Item", item.name, "custom_reagent_specification"))

	def test_item_change_rejected(self):
		frappe.db.rollback()
		first = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test RSpec First Item", "item_group": "Products"}
		).insert()
		second = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test RSpec Second Item", "item_group": "Products"}
		).insert()
		spec = frappe.get_doc(
			{
				"doctype": "Reagent Specification",
				"item": first.name,
				"reagent_role": "Test Reagent",
				"default_tests_per_pack": 100,
				"default_cogs_per_pack": 50,
			}
		).insert()
		spec.item = second.name
		with self.assertRaises(frappe.ValidationError):
			spec.save()

	def test_analyzer_item_cannot_have_reagent_specification(self):
		frappe.db.rollback()
		analyzer = frappe.get_doc(
			{"doctype": "Item", "item_code": "_Test RSpec Analyzer Item", "item_group": "Products"}
		).insert()
		frappe.get_doc({"doctype": "Analyzer Profile", "analyzer_item": analyzer.name}).insert()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Reagent Specification",
					"item": analyzer.name,
					"reagent_role": "Test Reagent",
				}
			).insert()
