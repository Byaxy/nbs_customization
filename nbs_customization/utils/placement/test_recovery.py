# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.tests.placement_contracts import (
	make_contract_kit,
	make_payment,
	make_si,
)
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


class TestRecoveryRecompute(IntegrationTestCase):
	def test_recompute_updates_contract(self):
		ctx = make_contract_kit("_TST-REC", target=12000)
		ct = ctx["contract"].name
		si1 = make_si(ctx, 20, 200, "2026-07-10", "Contract Reagent Sale")
		si2 = make_si(ctx, 10, 200, "2026-07-12", "Contract Consumable Replenishment")
		make_payment(si1)
		pe = make_payment(si2)
		pe.cancel()
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		part = get_payment_entry("Sales Invoice", si2.name)
		part.paid_to = "ECOBANK Current Account - USD - NBS"
		part.mode_of_payment = "Wire Transfer"
		part.reference_no = f"REF-PART-{si2.name}"
		part.reference_date = frappe.utils.today()
		part.references[0].allocated_amount = 500
		part.paid_amount = 500
		part.received_amount = 500
		part.insert(ignore_permissions=True)
		part.submit()

		result = recompute_contract_recovery(ct)
		self.assertEqual(result["cumulative_invoiced"], 6000)
		self.assertEqual(result["cumulative_collected"], 4500)
		self.assertEqual(result["outstanding_on_contract"], 7500)
		self.assertAlmostEqual(result["recovery_pct_invoiced"], 50)
		self.assertAlmostEqual(result["recovery_pct_collected"], 37.5)

		doc = frappe.get_doc("Instrument Placement Contract", ct)
		self.assertEqual(doc.cumulative_invoiced, 6000)
		self.assertEqual(doc.cumulative_collected, 4500)

	def test_recompute_zero_target(self):
		ctx = make_contract_kit("_TST-RECZ", target=0)
		make_si(ctx, 5, 200, "2026-07-10", "Contract Reagent Sale")
		result = recompute_contract_recovery(ctx["contract"].name)
		self.assertEqual(result["cumulative_invoiced"], 1000)
		self.assertEqual(result["recovery_pct_invoiced"], 0)
		self.assertEqual(result["recovery_pct_collected"], 0)

	def test_payment_entry_triggers_recompute(self):
		ctx = make_contract_kit("_TST-RECPE", target=12000)
		ct = ctx["contract"].name
		si = make_si(ctx, 20, 200, "2026-07-10", "Contract Reagent Sale")
		make_payment(si)
		doc = frappe.get_doc("Instrument Placement Contract", ct)
		self.assertEqual(doc.cumulative_collected, 4000)
		self.assertEqual(doc.outstanding_on_contract, 8000)

		ignored = make_si(ctx, 10, 200, "2026-07-12", "Contract Reagent Sale", counts=0)
		doc.reload()
		self.assertEqual(doc.cumulative_invoiced, 4000)

		si.reload()
		si.cancel()
		doc.reload()
		self.assertEqual(doc.cumulative_invoiced, 0)
		self.assertEqual(doc.cumulative_collected, 0)
		self.assertEqual(doc.outstanding_on_contract, 12000)
		ignored.reload()
		ignored.cancel()

	def test_full_collection_fulfills_active_contract(self):
		ctx = make_contract_kit("_TST-RECF", target=12000)
		ct = ctx["contract"].name
		for d in ("2026-07-10", "2026-07-12", "2026-07-14"):
			make_payment(make_si(ctx, 20, 200, d, "Contract Reagent Sale"))
		doc = frappe.get_doc("Instrument Placement Contract", ct)
		self.assertEqual(doc.cumulative_collected, 12000)
		self.assertEqual(doc.contract_status, "Fulfilled")

	def test_partial_collection_keeps_active(self):
		ctx = make_contract_kit("_TST-RECP", target=12000)
		ct = ctx["contract"].name
		make_payment(make_si(ctx, 20, 200, "2026-07-10", "Contract Reagent Sale"))
		doc = frappe.get_doc("Instrument Placement Contract", ct)
		self.assertEqual(doc.cumulative_collected, 4000)
		self.assertEqual(doc.contract_status, "Active")

	def test_free_issue_excluded(self):
		ctx = make_contract_kit("_TST-RECCPT", contract_type="CPT", target=60000)
		free = make_si(ctx, 30, 200, "2026-07-10", "Contract Reagent Sale", counts=0)
		counted = make_si(ctx, 5, 200, "2026-07-12", "Contract Reagent Sale", counts=1)
		result = recompute_contract_recovery(ctx["contract"].name)
		self.assertEqual(result["cumulative_invoiced"], 1000)
		self.assertEqual(free.grand_total, 6000)
		self.assertEqual(counted.grand_total, 1000)
