# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.tests.placement_contracts import make_contract_kit, make_deployed
from nbs_customization.tests.placement_fixtures import skip_test_record_bootstrap


class TestDeploymentAcceptance(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Deployment Acceptance")
		super().setUpClass()

	def _deployed(self, prefix):
		ctx = make_contract_kit(prefix)
		dep = make_deployed(ctx)
		return ctx, dep

	def _acceptance(self, deployment, **overrides):
		values = {
			"doctype": "Deployment Acceptance",
			"deployment": deployment.name,
			"acceptance_date": frappe.utils.today(),
			"customer_signed": 1,
		}
		values.update(overrides)
		return frappe.get_doc(values)

	def test_field_engineer_has_deployment_read_access(self):
		rows = [
			row
			for row in frappe.get_meta("Analyzer Deployment").permissions
			if row.role == "Field Engineer" and row.read
		]
		self.assertTrue(rows)

	def test_submit_updates_deployment(self):
		_ctx, dep = self._deployed("_TST-ACC1")
		acc = self._acceptance(dep).insert()
		acc.submit()
		dep.reload()
		self.assertEqual(dep.acceptance_document, acc.name)
		self.assertEqual(dep.acceptance_signed, 1)
		self.assertEqual(frappe.utils.getdate(dep.acceptance_date), frappe.utils.getdate(acc.acceptance_date))

	def test_matches_deployment_parties(self):
		_ctx, dep = self._deployed("_TST-ACC2")
		acc = self._acceptance(dep).insert()
		self.assertEqual(acc.contract, dep.contract)
		self.assertEqual(acc.asset, dep.asset)
		self.assertEqual(acc.customer, dep.customer)
		self.assertEqual(acc.customer_site, dep.customer_site)

	def test_duplicate_submitted_acceptance_blocked(self):
		_ctx, dep = self._deployed("_TST-ACC3")
		first = self._acceptance(dep).insert()
		first.submit()
		second = self._acceptance(dep)
		with self.assertRaises(frappe.ValidationError):
			second.insert()

	def test_draft_deployment_blocked(self):
		ctx = make_contract_kit("_TST-ACC4")
		dep = frappe.get_doc(
			{
				"doctype": "Analyzer Deployment",
				"naming_series": "NBSAD-.YYYY./.####",
				"contract": ctx["contract"].name,
				"asset": ctx["asset"].name,
				"customer": ctx["customer"].name,
				"customer_site": ctx["site"].name,
				"asset_location": "Block 1",
				"asset_storage_location": "Field 1",
				"deployment_date": frappe.utils.today(),
				"deployment_status": "Draft",
			}
		).insert()
		with self.assertRaises(frappe.ValidationError):
			self._acceptance(dep).insert()

	def test_submit_requires_customer_signature(self):
		_ctx, dep = self._deployed("_TST-ACC5")
		acc = self._acceptance(dep, customer_signed=0).insert()
		with self.assertRaises(frappe.ValidationError):
			acc.submit()

	def test_cancel_clears_deployment_mirrors(self):
		_ctx, dep = self._deployed("_TST-ACC6")
		acc = self._acceptance(dep).insert()
		acc.submit()
		acc.cancel()
		dep.reload()
		self.assertFalse(dep.acceptance_document)
		self.assertFalse(dep.acceptance_signed)
		self.assertFalse(dep.acceptance_date)

	def test_delete_clears_linked_deployment_mirrors(self):
		_ctx, dep = self._deployed("_TST-ACC7")
		acc = self._acceptance(dep).insert()
		frappe.db.set_value(
			"Analyzer Deployment",
			dep.name,
			{
				"acceptance_document": acc.name,
				"acceptance_signed": 1,
				"acceptance_date": acc.acceptance_date,
			},
		)
		frappe.delete_doc("Deployment Acceptance", acc.name, force=True)
		dep.reload()
		self.assertFalse(dep.acceptance_document)
		self.assertFalse(dep.acceptance_signed)
		self.assertFalse(dep.acceptance_date)

	def test_deployment_has_no_acceptance_attachment_field(self):
		self.assertFalse(frappe.get_meta("Analyzer Deployment").has_field("acceptance_attachment"))
