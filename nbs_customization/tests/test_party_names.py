# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.api import get_party_names


class TestPartyNames(IntegrationTestCase):
	def test_customer_and_supplier_names_are_keyed_by_id(self):
		stamp = frappe.generate_hash(length=8)
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"_Test Party Customer {stamp}",
				"customer_type": "Company",
			}
		).insert()
		supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"_Test Party Supplier {stamp}",
			}
		).insert()

		names = get_party_names()

		self.assertEqual(names[customer.name], customer.customer_name)
		self.assertEqual(names[supplier.name], supplier.supplier_name)
