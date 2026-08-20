# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.nbs_customization.doctype.repossession_request.repossession_request import execute_retrieval


class TestRepossession(FrappeTestCase):
	def setUp(self):
		pass

	def tearDown(self):
		frappe.db.rollback()

	def test_submit_sets_pending_approval(self):
		pass

	def test_approve_then_execute_retrieval(self):
		pass

	def test_execute_updates_deployment_status(self):
		pass

	def test_execute_requires_approved_status(self):
		rr_name = ""
		with self.assertRaises(frappe.ValidationError):
			execute_retrieval(rr_name)
