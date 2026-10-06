# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from nbs_customization.controllers.placement.amendment import mark_effective
from nbs_customization.nbs_customization.doctype.instrument_pricing_worksheet.instrument_pricing_worksheet import (
	make_instrument_placement_contract,
)
from nbs_customization.tasks import daily_process_amendments
from nbs_customization.tests.placement_contracts import (
	make_asset,
	make_contract_kit,
	make_worksheet,
)
from nbs_customization.tests.placement_fixtures import skip_test_record_bootstrap


class TestContractAmendment(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Contract Amendment")
		super().setUpClass()

	def _amendment(self, ctx, **overrides):
		args = {
			"doctype": "Contract Amendment",
			"contract": ctx["contract"].name,
			"amendment_date": today(),
			"effective_date": today(),
			"reason": "Customer Volume Change Request",
			"new_declared_volume": 200,
			"status": "Approved",
		}
		args.update(overrides)
		return frappe.get_doc(args).insert()

	def test_submit_sets_pending_customer_signature(self):
		ctx = make_contract_kit("_TST-AMD0")
		am = self._amendment(ctx, status="Draft")
		am.submit()
		self.assertEqual(
			frappe.db.get_value("Contract Amendment", am.name, "status"),
			"Pending Customer Signature",
		)

	def test_approve_button_saves_after_submit(self):
		# Approve Amendment button path: set_value + save on submitted doc.
		ctx = make_contract_kit("_TST-AMD9")
		am = self._amendment(ctx, status="Draft")
		am.submit()
		am.status = "Approved"
		am.approved_by = "Administrator"
		am.save()
		self.assertEqual(
			frappe.db.get_value("Contract Amendment", am.name, "status"),
			"Approved",
		)
		mark_effective(am.name)
		self.assertEqual(
			frappe.db.get_value("Contract Amendment", am.name, "status"),
			"Effective",
		)

	def test_apply_volume_updates_lines(self):
		ctx = make_contract_kit("_TST-AMD1")
		am = self._amendment(ctx)
		am.apply_to_contract()
		ct = frappe.get_doc("Instrument Placement Contract", ctx["contract"].name)
		for line in ct.contract_reagent_lines:
			self.assertEqual(line.monthly_test_volume, 200)
			# ceil(200 / tests-per-pack 100) via cogs_per_unit + reagent spec.
			self.assertEqual(line.min_monthly_qty, 2)
		am.reload()
		self.assertEqual(am.status, "Effective")

	def test_apply_volume_on_server_mapped_contract_uses_pack_size(self):
		# Contracts mapped via make_instrument_placement_contract must carry
		# cogs_per_unit, or the amendment divisor falls back to 1 and the
		# monthly charge inflates to the full volume.
		ctx = make_contract_kit("_TST-AMD7")
		ws2 = make_worksheet(
			"_TST-AMD7W",
			ctx["analyzer"],
			ctx["reagent"],
			ctx["analyzer"],
			ctx["customer"],
		)
		# Server mapping copies the analyzer description (mandatory on Contract).
		frappe.db.set_value("Item", ctx["analyzer"]["item"].name, "description", "Test analyzer")
		asset2 = make_asset("_TST-AMD7B", ctx["category"], "_TST-AMD7B-SN", ctx["analyzer"]["item"].name)
		frappe.flags.args = {"asset": asset2.name, "customer_site": ctx["site"].name}
		try:
			mapped = make_instrument_placement_contract(ws2.name)
		finally:
			frappe.flags.args = {}
		mapped.insert()
		mapped.submit()
		am = self._amendment({"contract": mapped})
		am.apply_to_contract()
		ct = frappe.get_doc("Instrument Placement Contract", mapped.name)
		line = ct.contract_reagent_lines[0]
		self.assertEqual(line.monthly_test_volume, 200)
		self.assertEqual(line.min_monthly_qty, 2)
		am.reload()
		self.assertEqual(am.status, "Effective")

	def test_apply_value_share_worksheet_target(self):
		ctx = make_contract_kit("_TST-AMD2")
		ws2 = make_worksheet(
			"_TST-AMD2W",
			ctx["analyzer"],
			ctx["reagent"],
			ctx["analyzer"],
			ctx["customer"],
		)
		am = self._amendment(
			ctx,
			new_min_value=9999,
			new_share_pct=35,
			new_pricing_worksheet=ws2.name,
		)
		am.apply_to_contract()
		ct = frappe.get_doc("Instrument Placement Contract", ctx["contract"].name)
		self.assertEqual(ct.min_monthly_value, 9999)
		self.assertEqual(ct.revenue_share_pct, 35)
		self.assertEqual(ct.pricing_worksheet, ws2.name)

		# new_recovery_target is fetch-driven on the form — set it directly
		# to assert the controller applies an explicit target.
		am2 = self._amendment(ctx, new_declared_volume=100)
		am2.db_set("new_recovery_target", 77777)
		am2.apply_to_contract()
		ct.reload()
		self.assertEqual(ct.total_recovery_target, 77777)

	def test_mark_effective_delegates(self):
		ctx = make_contract_kit("_TST-AMD3")
		am = self._amendment(ctx)
		self.assertTrue(mark_effective(am.name))
		am.reload()
		self.assertEqual(am.status, "Effective")
		am2 = self._amendment(ctx, new_declared_volume=300, status="Draft")
		with self.assertRaises(frappe.ValidationError):
			mark_effective(am2.name)

	def test_daily_job_applies_due_only(self):
		ctx = make_contract_kit("_TST-AMD4")
		due = self._amendment(ctx)
		future = self._amendment(
			ctx,
			new_declared_volume=300,
			effective_date=add_days(today(), 30),
		)
		daily_process_amendments()
		due.reload()
		future.reload()
		self.assertEqual(due.status, "Effective")
		self.assertEqual(future.status, "Approved")
		ct = frappe.get_doc("Instrument Placement Contract", ctx["contract"].name)
		self.assertEqual(ct.contract_reagent_lines[0].monthly_test_volume, 200)

	def test_non_approved_reapply_blocked(self):
		ctx = make_contract_kit("_TST-AMD5")
		am = self._amendment(ctx, status="Draft")
		with self.assertRaises(frappe.ValidationError):
			am.apply_to_contract()
		am.db_set("status", "Effective")
		am.reload()
		with self.assertRaises(frappe.ValidationError):
			am.apply_to_contract()

	def test_recovery_target_below_collected_blocked(self):
		ctx = make_contract_kit("_TST-AMD6")
		frappe.db.set_value(
			"Instrument Placement Contract", ctx["contract"].name, "cumulative_collected", 5000
		)
		am = self._amendment(ctx)
		am.db_set("new_recovery_target", 1000)
		am.reload()
		with self.assertRaises(frappe.ValidationError):
			am.apply_to_contract()
