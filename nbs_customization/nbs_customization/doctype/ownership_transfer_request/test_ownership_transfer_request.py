# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.nbs_customization.doctype.ownership_transfer_request.ownership_transfer_request import complete_transfer


class TestOwnershipTransfer(FrappeTestCase):
	def setUp(self):
		pass

	def tearDown(self):
		frappe.db.rollback()

	def test_non_rlo_contract_blocked(self):
		pass

	def test_eligible_contract_allows_otr(self):
		pass

	def test_complete_transfer_fulfills_contract(self):
		pass

	def test_complete_transfer_requires_certificate(self):
		otr_name = ""
		with self.assertRaises(frappe.ValidationError):
			complete_transfer(otr_name)
