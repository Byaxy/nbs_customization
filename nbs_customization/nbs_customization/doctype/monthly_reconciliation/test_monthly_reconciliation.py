# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.nbs_customization.doctype.monthly_reconciliation.monthly_reconciliation import (
	create_penalty_invoice,
	generate_monthly_reconciliation,
)
from nbs_customization.tests.placement_contracts import (
	make_contract_kit,
	make_deployed,
	make_si,
)
from nbs_customization.tests.placement_fixtures import skip_test_record_bootstrap


class TestMonthlyReconciliation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Monthly Reconciliation")
		super().setUpClass()

	def test_generates_and_aggregates(self):
		ctx = make_contract_kit("_TST-MRC1")
		si1 = make_si(ctx, 20, 200, "2026-07-10", "Contract Reagent Sale")
		si2 = make_si(ctx, 10, 200, "2026-07-12", "Contract Consumable Replenishment")
		outside = make_si(ctx, 5, 200, "2026-08-02", "Contract Reagent Sale")

		name = generate_monthly_reconciliation(ctx["contract"].name, "2026-07")
		mrc = frappe.get_doc("Monthly Reconciliation", name)
		self.assertEqual(mrc.actual_reagent_value, 4000)
		self.assertEqual(mrc.actual_consumable_value, 2000)
		self.assertEqual(mrc.total_actual_value, 6000)
		self.assertEqual(len(mrc.linked_invoices), 2)
		names = {r.sales_invoice for r in mrc.linked_invoices}
		self.assertEqual(names, {si1.name, si2.name})
		self.assertNotIn(outside.name, names)
		self.assertEqual(mrc.compliance_status, "Compliant")

		with self.assertRaises(frappe.ValidationError):
			cpt = make_contract_kit("_TST-MRC1C", contract_type="CPT")
			generate_monthly_reconciliation(cpt["contract"].name, "2026-07")

	def test_shortfall_increments_breach(self):
		ctx = make_contract_kit("_TST-MRC2", target=50000, breach=3, grace=0, minqty=100)
		frappe.db.set_value(
			"Instrument Placement Contract",
			ctx["contract"].name,
			"consecutive_breach_count",
			2,
		)
		make_si(ctx, 2, 200, "2026-07-15", "Contract Reagent Sale")

		name = generate_monthly_reconciliation(ctx["contract"].name, "2026-07")
		mrc = frappe.get_doc("Monthly Reconciliation", name)
		self.assertEqual(mrc.compliance_status, "Shortfall")
		self.assertEqual(mrc.consecutive_breach_count, 3)
		self.assertEqual(mrc.shortfall_value, 15000 - 400)
		self.assertEqual(
			frappe.db.get_value(
				"Instrument Placement Contract",
				ctx["contract"].name,
				"consecutive_breach_count",
			),
			3,
		)

	def test_grace_period_holds_count(self):
		ctx = make_contract_kit("_TST-MRC3", breach=2, grace=60)
		name = generate_monthly_reconciliation(ctx["contract"].name, "2026-09")
		mrc = frappe.get_doc("Monthly Reconciliation", name)
		self.assertEqual(mrc.compliance_status, "Grace Period")
		self.assertEqual(mrc.consecutive_breach_count, 0)
		self.assertEqual(
			frappe.db.get_value(
				"Instrument Placement Contract",
				ctx["contract"].name,
				"consecutive_breach_count",
			),
			0,
		)

	def test_threshold_auto_creates_repossession(self):
		ctx = make_contract_kit("_TST-MRC4", target=50000, breach=1, grace=0, minqty=100)
		make_deployed(ctx)
		make_si(ctx, 2, 200, "2026-07-15", "Contract Reagent Sale")

		name = generate_monthly_reconciliation(ctx["contract"].name, "2026-07")
		mrc = frappe.get_doc("Monthly Reconciliation", name)
		rrs = frappe.db.get_all(
			"Repossession Request",
			filters={"contract": ctx["contract"].name},
			fields=["name", "status", "reason", "breach_count", "months_breached"],
		)
		self.assertEqual(len(rrs), 1)
		self.assertEqual(rrs[0].status, "Draft")
		self.assertEqual(rrs[0].reason, "Minimum Purchase Breach")
		self.assertEqual(rrs[0].breach_count, mrc.consecutive_breach_count)

		# Below threshold → none; existing open RR → no duplicate; regenerate idempotent.
		ctx2 = make_contract_kit("_TST-MRC5", target=50000, breach=5, grace=0, minqty=100)
		make_deployed(ctx2)
		make_si(ctx2, 2, 200, "2026-07-15", "Contract Reagent Sale")
		generate_monthly_reconciliation(ctx2["contract"].name, "2026-07")
		self.assertEqual(
			frappe.db.count("Repossession Request", {"contract": ctx2["contract"].name}),
			0,
		)
		again = generate_monthly_reconciliation(ctx["contract"].name, "2026-07")
		self.assertEqual(again, name)
		self.assertEqual(
			frappe.db.count("Repossession Request", {"contract": ctx["contract"].name}),
			1,
		)

	def test_penalty_invoice_guards(self):
		ctx = make_contract_kit("_TST-MRC6", target=50000, breach=3, grace=0, minqty=100)
		make_si(ctx, 2, 200, "2026-07-15", "Contract Reagent Sale")
		short = frappe.get_doc(
			"Monthly Reconciliation",
			generate_monthly_reconciliation(ctx["contract"].name, "2026-07"),
		)
		self.assertEqual(short.compliance_status, "Shortfall")

		ctx2 = make_contract_kit("_TST-MRC7")
		make_si(ctx2, 20, 200, "2026-07-10", "Contract Reagent Sale")
		good = frappe.get_doc(
			"Monthly Reconciliation",
			generate_monthly_reconciliation(ctx2["contract"].name, "2026-07"),
		)
		with self.assertRaises(frappe.ValidationError):
			create_penalty_invoice(good.name)

	def test_penalty_invoice_creates(self):
		from nbs_customization.setup import create_shortfall_penalty_item

		create_shortfall_penalty_item()
		ctx = make_contract_kit("_TST-MRC8", target=50000, breach=3, grace=0, minqty=100)
		make_si(ctx, 2, 200, "2026-07-15", "Contract Reagent Sale")
		short = frappe.get_doc(
			"Monthly Reconciliation",
			generate_monthly_reconciliation(ctx["contract"].name, "2026-07"),
		)
		si_name = create_penalty_invoice(short.name)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.submit()
		self.assertEqual(si.items[0].item_code, "SHORTFALL-PENALTY")
		short.reload()
		self.assertEqual(short.penalty_invoice, si_name)
		with self.assertRaises(frappe.ValidationError):
			create_penalty_invoice(short.name)
