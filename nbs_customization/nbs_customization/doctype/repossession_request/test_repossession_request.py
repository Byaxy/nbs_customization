# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.nbs_customization.doctype.repossession_request.repossession_request import (
	execute_retrieval,
)
from nbs_customization.tests.placement_contracts import (
	make_contract_kit,
	make_deployed,
)
from nbs_customization.tests.placement_fixtures import skip_test_record_bootstrap


class TestRepossession(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Repossession Request")
		super().setUpClass()

	def _draft_rr(self, prefix, reason="Minimum Purchase Breach", **kw):
		ctx = make_contract_kit(prefix)
		dep = make_deployed(ctx)
		args = {
			"doctype": "Repossession Request",
			"naming_series": "NBSRPR-.YYYY./.####",
			"contract": ctx["contract"].name,
			"analyzer_deployment": dep.name,
			"reason": reason,
			"requested_by": "Administrator",
			"request_date": frappe.utils.today(),
			"status": "Draft",
		}
		args.update(kw)
		if reason == "Minimum Purchase Breach":
			args.setdefault("breach_count", 2)
			args.setdefault("months_breached", 2)
		else:
			args.setdefault("unpaid_statements", 2)
		rr = frappe.get_doc(args).insert()
		return ctx, dep, rr

	def test_submit_sets_pending_approval(self):
		_ctx, _dep, rr = self._draft_rr("_TST-RP1")
		rr.submit()
		self.assertEqual(
			frappe.db.get_value("Repossession Request", rr.name, "status"),
			"Pending Approval",
		)

	def test_approve_saves_after_submit(self):
		# Approve button path: set_value + save on the submitted doc.
		_ctx, _dep, rr = self._draft_rr("_TST-RP5")
		rr.submit()
		rr.status = "Approved"
		rr.approved_by = "Administrator"
		rr.approval_date = frappe.utils.today()
		rr.save()
		self.assertEqual(
			frappe.db.get_value("Repossession Request", rr.name, "status"),
			"Approved",
		)

	def test_illegal_transition_raises(self):
		_ctx, _dep, rr = self._draft_rr("_TST-RP2")
		rr.status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			rr.save()

	def test_approve_then_execute_retrieval(self):
		ctx, dep, rr = self._draft_rr(
			"_TST-RP3",
			reason="Non-Payment of Revenue Share",
		)
		rr.submit()
		frappe.db.set_value("Repossession Request", rr.name, "status", "Approved")
		frappe.db.set_value(
			"Repossession Request",
			rr.name,
			"actual_retrieval_date",
			frappe.utils.today(),
		)
		out = execute_retrieval(rr.name)
		self.assertEqual(out, dep.name)
		dep.reload()
		self.assertEqual(dep.deployment_status, "Permanently Retrieved")
		self.assertEqual(dep.retrieval_reason, "Contract Breach")
		self.assertEqual(dep.repossession_request, rr.name)
		self.assertEqual(
			frappe.db.get_value("Repossession Request", rr.name, "status"),
			"Analyzer Retrieved",
		)
		self.assertEqual(
			frappe.db.get_value(
				"Asset",
				ctx["asset"].name,
				"custom_current_deployment_status",
			),
			"Warehouse",
		)
		self.assertIsNone(
			frappe.db.get_value(
				"Asset",
				ctx["asset"].name,
				"custom_current_placement_contract",
			),
		)

	def test_execute_requires_approved_status(self):
		_ctx, _dep, rr = self._draft_rr("_TST-RP4")
		with self.assertRaises(frappe.ValidationError):
			execute_retrieval(rr.name)
