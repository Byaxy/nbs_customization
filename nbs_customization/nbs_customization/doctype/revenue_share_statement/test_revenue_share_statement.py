# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.nbs_customization.doctype.revenue_share_statement.revenue_share_statement import (
	_resolve_declared_volume,
	generate_revenue_share_statement,
)
from nbs_customization.tests.placement_contracts import make_contract_kit
from nbs_customization.tests.placement_fixtures import (
	ensure_stock,
	skip_test_record_bootstrap,
)


class TestRevenueShareStatement(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Revenue Share Statement")
		super().setUpClass()

	def _cpt(self, prefix):
		ctx = make_contract_kit(
			prefix,
			contract_type="CPT",
			target=60000,
			agreed_price=600,
			share_pct=20,
		)
		ensure_stock(ctx["reagent"].name, qty=50)
		return ctx

	def test_statement_math_and_free_issue_dn(self):
		from nbs_customization.setup import create_revenue_share_fee_item

		create_revenue_share_fee_item()
		ctx = self._cpt("_TST-RSS1")
		generate_revenue_share_statement(ctx["contract"].name, "2026-07")
		rss = frappe.get_doc(
			"Revenue Share Statement",
			{"contract": ctx["contract"].name, "period": "2026-07"},
		)
		self.assertEqual(rss.declared_volume, 100)
		self.assertEqual(rss.gross_revenue, 60000)
		self.assertEqual(rss.our_share_amount, 12000)
		self.assertEqual(rss.customer_share_amount, 48000)
		self.assertTrue(rss.waybill_kit_dispatch)
		self.assertTrue(rss.sales_invoice)
		dn = frappe.get_doc("Delivery Note", rss.waybill_kit_dispatch)
		self.assertEqual(dn.docstatus, 1)
		self.assertEqual(dn.custom_placement_transaction_type, "Contract Free Issue")
		for row in dn.items:
			self.assertEqual(row.rate, 0)
			self.assertGreater(row.qty, 0)

	def test_statement_and_invoice_created(self):
		from nbs_customization.setup import create_revenue_share_fee_item

		create_revenue_share_fee_item()
		ctx = self._cpt("_TST-RSS2")
		name = generate_revenue_share_statement(ctx["contract"].name, "2026-07")
		rss = frappe.get_doc("Revenue Share Statement", name)
		self.assertEqual(rss.status, "Invoiced")
		si = frappe.get_doc("Sales Invoice", rss.sales_invoice)
		self.assertEqual(si.docstatus, 1)
		self.assertEqual(si.items[0].item_code, "REVENUE-SHARE-FEE")
		self.assertEqual(si.grand_total, 12000)
		ct = frappe.get_doc("Instrument Placement Contract", ctx["contract"].name)
		self.assertEqual(ct.cumulative_invoiced, 12000)

	def test_amendment_volume_overrides(self):
		ctx = self._cpt("_TST-RSS3")
		frappe.get_doc(
			{
				"doctype": "Contract Amendment",
				"contract": ctx["contract"].name,
				"amendment_date": "2026-07-05",
				"effective_date": "2026-07-05",
				"reason": "Customer Volume Change Request",
				"new_declared_volume": 250,
				"status": "Effective",
			}
		).insert()
		contract = frappe.get_doc("Instrument Placement Contract", ctx["contract"].name)
		self.assertEqual(_resolve_declared_volume(contract, "2026-07"), 250)
		self.assertEqual(_resolve_declared_volume(contract, "2026-08"), 100)

	def test_idempotent(self):
		from nbs_customization.setup import create_revenue_share_fee_item

		create_revenue_share_fee_item()
		ctx = self._cpt("_TST-RSS4")
		generate_revenue_share_statement(ctx["contract"].name, "2026-07")
		first = frappe.db.get_value(
			"Revenue Share Statement",
			{"contract": ctx["contract"].name, "period": "2026-07"},
			"name",
		)
		dn_count = frappe.db.count(
			"Delivery Note",
			{"custom_instrument_placement_contract": ctx["contract"].name},
		)
		second = generate_revenue_share_statement(ctx["contract"].name, "2026-07")
		self.assertEqual(second, first)
		self.assertEqual(
			frappe.db.count(
				"Delivery Note",
				{"custom_instrument_placement_contract": ctx["contract"].name},
			),
			dn_count,
		)

	def test_rra_rejected(self):
		ctx = make_contract_kit("_TST-RSS5")
		with self.assertRaises(frappe.ValidationError):
			generate_revenue_share_statement(ctx["contract"].name, "2026-07")
