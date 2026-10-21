# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.nbs_customization.doctype.revenue_share_statement.revenue_share_statement import (
	_compute_kits_per_line,
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
		# Worksheet economics tuned so the computed share is exactly 20%:
		# final 288000 on 1440000 gross (T=100, price 600, Ca 199000).
		ctx = make_contract_kit(
			prefix,
			contract_type="CPT",
			target=60000,
			monthly_test_volume=100,
			price_per_test=600,
			analyzer_landed_cost=199000,
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
		amendment_doc = frappe.get_doc(
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
		volume, amendment = _resolve_declared_volume(contract, "2026-07")
		self.assertEqual(volume, 250)
		self.assertEqual(amendment, amendment_doc.name)
		volume, amendment = _resolve_declared_volume(contract, "2026-08")
		self.assertEqual(volume, 100)
		self.assertIsNone(amendment)

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

	def test_free_issue_survives_standard_selling_price(self):
		# Production has Standard Selling prices: core reprices falsy rates
		# from the price list during validate — free-issue lines must stay 0.
		from nbs_customization.setup import create_revenue_share_fee_item

		create_revenue_share_fee_item()
		ctx = self._cpt("_TST-RSS6")
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": ctx["reagent"].name,
				"price_list": "Standard Selling",
				"price_list_rate": 200,
			}
		).insert()
		name = generate_revenue_share_statement(ctx["contract"].name, "2026-07")
		rss = frappe.get_doc("Revenue Share Statement", name)
		dn = frappe.get_doc("Delivery Note", rss.waybill_kit_dispatch)
		for row in dn.items:
			self.assertEqual(row.rate, 0)
			self.assertEqual(row.amount, 0)

	def test_regenerate_after_invoice_cancelled(self):
		from nbs_customization.setup import create_revenue_share_fee_item

		create_revenue_share_fee_item()
		ctx = self._cpt("_TST-RSS7")
		name = generate_revenue_share_statement(ctx["contract"].name, "2026-07")
		rss = frappe.get_doc("Revenue Share Statement", name)
		old_invoice = rss.sales_invoice
		frappe.get_doc("Sales Invoice", old_invoice).cancel()
		rss.db_set("gross_revenue", 1)
		generate_revenue_share_statement(ctx["contract"].name, "2026-07")
		rss.reload()
		self.assertNotEqual(rss.sales_invoice, old_invoice)
		self.assertEqual(
			frappe.db.get_value("Sales Invoice", rss.sales_invoice, "docstatus"),
			1,
		)

	def test_changed_volume_requires_dispatch_cancellation(self):
		from nbs_customization.setup import create_revenue_share_fee_item

		create_revenue_share_fee_item()
		ctx = self._cpt("_TST-RSS8")
		name = generate_revenue_share_statement(ctx["contract"].name, "2026-07")
		rss = frappe.get_doc("Revenue Share Statement", name)
		old_dn = rss.waybill_kit_dispatch
		frappe.get_doc("Sales Invoice", rss.sales_invoice).cancel()
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

		with self.assertRaises(frappe.ValidationError):
			generate_revenue_share_statement(ctx["contract"].name, "2026-07")

		frappe.get_doc("Delivery Note", old_dn).cancel()
		generate_revenue_share_statement(ctx["contract"].name, "2026-07")
		rss.reload()
		self.assertNotEqual(rss.waybill_kit_dispatch, old_dn)
		new_dn = frappe.get_doc("Delivery Note", rss.waybill_kit_dispatch)
		self.assertEqual(new_dn.docstatus, 1)
		self.assertEqual(sum(row.qty for row in new_dn.items), 3)

	def test_shared_reagent_packs_round_once_per_item(self):
		contract = frappe._dict(
			contract_reagent_lines=[
				frappe._dict(item_code="_TST-SHARED", monthly_test_volume=1),
				frappe._dict(item_code="_TST-SHARED", monthly_test_volume=1),
			]
		)
		with patch.object(frappe.db, "get_value", return_value=100):
			result = _compute_kits_per_line(contract, 80)
		self.assertEqual(result, {"_TST-SHARED": 1})

	def test_rra_rejected(self):
		ctx = make_contract_kit("_TST-RSS5")
		with self.assertRaises(frappe.ValidationError):
			generate_revenue_share_statement(ctx["contract"].name, "2026-07")
