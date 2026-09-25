# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.nbs_customization.doctype.ownership_transfer_request.ownership_transfer_request import (
	complete_transfer,
	create_ownership_transfer_request,
)
from nbs_customization.tests.placement_contracts import (
	make_contract_kit,
	make_deployed,
)
from nbs_customization.tests.placement_fixtures import skip_test_record_bootstrap


class TestOwnershipTransfer(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Ownership Transfer Request")
		super().setUpClass()

	def _rlo(self, prefix, threshold=1, outstanding=0):
		ctx = make_contract_kit(prefix, contract_type="RLO", target=12000)
		frappe.db.set_value(
			"Instrument Placement Contract",
			ctx["contract"].name,
			"ownership_threshold_met",
			threshold,
		)
		frappe.db.set_value(
			"Instrument Placement Contract",
			ctx["contract"].name,
			"outstanding_on_contract",
			outstanding,
		)
		return ctx

	def test_non_rlo_contract_blocked(self):
		ctx = make_contract_kit("_TST-OT1")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Ownership Transfer Request",
					"naming_series": "NBSOTR-YYYY./.####",
					"contract": ctx["contract"].name,
					"status": "Draft",
				}
			).insert()

	def test_below_threshold_and_outstanding_blocked(self):
		ctx = self._rlo("_TST-OT2", threshold=0)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Ownership Transfer Request",
					"naming_series": "NBSOTR-YYYY./.####",
					"contract": ctx["contract"].name,
					"status": "Draft",
				}
			).insert()
		ctx = self._rlo("_TST-OT3", threshold=1, outstanding=5000)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Ownership Transfer Request",
					"naming_series": "NBSOTR-YYYY./.####",
					"contract": ctx["contract"].name,
					"status": "Draft",
				}
			).insert()

	def test_eligible_contract_allows_otr(self):
		ctx = self._rlo("_TST-OT4")
		name = create_ownership_transfer_request(ctx["contract"].name)
		otr = frappe.get_doc("Ownership Transfer Request", name)
		self.assertEqual(otr.status, "Draft")
		self.assertEqual(otr.contract, ctx["contract"].name)
		# No duplicate while one is open.
		self.assertEqual(create_ownership_transfer_request(ctx["contract"].name), name)

	def test_approval_buttons_save_after_submit(self):
		# Finance/Legal button path: set_value + save on the submitted doc.
		ctx = self._rlo("_TST-OT7")
		name = create_ownership_transfer_request(ctx["contract"].name)
		otr = frappe.get_doc("Ownership Transfer Request", name)
		otr.submit()
		otr.finance_reviewed_by = "Administrator"
		otr.finance_review_date = frappe.utils.today()
		otr.status = "Pending Legal Review"
		otr.save()
		otr.reload()
		otr.legal_reviewed_by = "Administrator"
		otr.legal_review_date = frappe.utils.today()
		otr.status = "Approved"
		otr.save()
		self.assertEqual(
			frappe.db.get_value("Ownership Transfer Request", name, "status"),
			"Approved",
		)

	def test_complete_transfer_fulfills_contract(self):
		ctx = self._rlo("_TST-OT5")
		dep = make_deployed(ctx)
		schedules = frappe.db.get_all(
			"Asset Depreciation Schedule",
			filters={"asset": ctx["asset"].name, "docstatus": 1},
			pluck="name",
		)
		self.assertTrue(schedules)
		name = create_ownership_transfer_request(ctx["contract"].name)
		frappe.db.set_value("Ownership Transfer Request", name, "status", "Approved")
		frappe.db.set_value(
			"Ownership Transfer Request",
			name,
			"transfer_certificate",
			"/files/cert.pdf",
		)
		complete_transfer(name)
		self.assertEqual(
			frappe.db.get_value("Ownership Transfer Request", name, "status"),
			"Transfer Completed",
		)
		self.assertEqual(
			frappe.db.get_value(
				"Instrument Placement Contract",
				ctx["contract"].name,
				"contract_status",
			),
			"Fulfilled",
		)
		self.assertEqual(
			frappe.db.get_value("Analyzer Deployment", dep.name, "deployment_status"),
			"Permanently Retrieved",
		)
		self.assertEqual(
			frappe.db.get_value("Analyzer Deployment", dep.name, "retrieval_reason"),
			"Ownership Transfer",
		)
		for s in schedules:
			self.assertEqual(
				frappe.db.get_value("Asset Depreciation Schedule", s, "docstatus"),
				2,
			)

	def test_complete_transfer_requires_certificate(self):
		ctx = self._rlo("_TST-OT6")
		make_deployed(ctx)
		name = create_ownership_transfer_request(ctx["contract"].name)
		frappe.db.set_value("Ownership Transfer Request", name, "status", "Approved")
		with self.assertRaises(frappe.ValidationError):
			complete_transfer(name)
