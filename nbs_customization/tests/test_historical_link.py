# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from nbs_customization.tests.placement_contracts import make_contract_kit
from nbs_customization.tests.placement_fixtures import (
	COMPANY,
	WAREHOUSE,
	ensure_stock,
	skip_test_record_bootstrap,
)
from nbs_customization.utils.placement.historical_link import (
	get_linkable_sales_orders,
	link_historical_sales_orders,
)

TEST_DATE = "2026-06-10"


class TestHistoricalLink(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Instrument Placement Contract")
		super().setUpClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _make_order(self, ctx, qty=5, item_code=None, rate=None, transaction_date=TEST_DATE):
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": COMPANY,
				"customer": ctx["customer"].name,
				"transaction_date": transaction_date,
				"delivery_date": transaction_date,
				"items": [
					{
						"item_code": item_code or ctx["reagent"].name,
						"qty": qty,
						"rate": rate
						if rate is not None
						else flt(ctx["contract"].contract_reagent_lines[0].contract_price),
						"warehouse": WAREHOUSE,
					}
				],
			}
		)
		so.insert()
		so.submit()
		return so

	def _make_invoice(self, ctx, qty=5, rate=None, sales_order=None):
		sales_order = sales_order or self._make_order(ctx, qty=qty, rate=rate)
		items = [
			{
				"item_code": ctx["reagent"].name,
				"qty": qty,
				"rate": rate
				if rate is not None
				else flt(ctx["contract"].contract_reagent_lines[0].contract_price),
				"sales_order": sales_order.name,
				"so_detail": sales_order.items[0].name,
			}
		]
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": ctx["customer"].name,
				"posting_date": TEST_DATE,
				"set_posting_time": 1,
				"items": items,
			}
		)
		si.insert()
		si.submit()
		return si

	def _make_delivery(self, ctx, qty=5, sales_order=None):
		ensure_stock(ctx["reagent"].name, qty=qty + 10, posting_date="2026-01-01")
		sales_order = sales_order or self._make_order(ctx, qty=qty)
		dn = frappe.get_doc(
			{
				"doctype": "Delivery Note",
				"company": COMPANY,
				"customer": ctx["customer"].name,
				"posting_date": TEST_DATE,
				"set_posting_time": 1,
				"items": [
					{
						"item_code": ctx["reagent"].name,
						"qty": qty,
						"rate": flt(ctx["contract"].contract_reagent_lines[0].contract_price),
						"warehouse": WAREHOUSE,
						"against_sales_order": sales_order.name,
						"so_detail": sales_order.items[0].name,
					}
				],
			}
		)
		dn.insert()
		dn.submit()
		return dn

	def test_candidates_are_only_unlinked_contract_orders_and_search_works(self):
		ctx = make_contract_kit("_TST-HL1")
		current = self._make_order(ctx, qty=5)
		older = self._make_order(ctx, qty=2, transaction_date="2025-12-01")

		other_item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_TST-HL1-OTHER",
				"item_group": "Products",
				"is_stock_item": 1,
				"stock_uom": "Nos",
			}
		).insert()
		unrelated = self._make_order(ctx, qty=1, item_code=other_item.name)

		rows = get_linkable_sales_orders(ctx["contract"].name)
		names = {row["name"] for row in rows}
		self.assertIn(current.name, names)
		self.assertIn(older.name, names)
		self.assertNotIn(unrelated.name, names)
		current_row = next(row for row in rows if row["name"] == current.name)
		self.assertEqual(current_row["suggested_type"], "Contract Reagent Sale")
		self.assertFalse(current_row["blocked"])

		search_rows = get_linkable_sales_orders(ctx["contract"].name, search=current.name)
		self.assertEqual([row["name"] for row in search_rows], [current.name])

		link_historical_sales_orders(ctx["contract"].name, [current.name])
		rows = get_linkable_sales_orders(ctx["contract"].name)
		self.assertNotIn(current.name, {row["name"] for row in rows})

	def test_sales_order_chain_links_invoice_and_delivery(self):
		ctx = make_contract_kit("_TST-HL2")
		so = self._make_order(ctx, qty=4)
		si = self._make_invoice(ctx, qty=4, sales_order=so)
		dn = self._make_delivery(ctx, qty=4, sales_order=so)

		result = link_historical_sales_orders(ctx["contract"].name, [so.name])
		self.assertEqual(result["sales_orders"], 1)
		self.assertEqual(result["sales_invoices"], 1)
		self.assertEqual(result["delivery_notes"], 1)

		for doc in (so, si, dn):
			doc.reload()
			self.assertEqual(doc.custom_instrument_placement_contract, ctx["contract"].name)
			self.assertEqual(doc.custom_placement_transaction_type, "Contract Reagent Sale")
		self.assertEqual(si.custom_counts_toward_recovery, 1)

		ctx["contract"].reload()
		self.assertEqual(ctx["contract"].cumulative_invoiced, si.grand_total)
		self.assertEqual(ctx["contract"].progress_reagent_delivered, 4)

	def test_sales_order_without_chain_links_order_only(self):
		ctx = make_contract_kit("_TST-HL3")
		so = self._make_order(ctx, qty=3)

		result = link_historical_sales_orders(ctx["contract"].name, [so.name])
		self.assertEqual(result["total"], 1)
		self.assertEqual(result["sales_invoices"], 0)
		self.assertEqual(result["delivery_notes"], 0)

		so.reload()
		ctx["contract"].reload()
		self.assertEqual(so.custom_instrument_placement_contract, ctx["contract"].name)
		self.assertEqual(ctx["contract"].cumulative_invoiced, 0)
		self.assertEqual(ctx["contract"].progress_reagent_delivered, 0)

	def test_link_is_idempotent_and_fulfilled_contract_allowed(self):
		ctx = make_contract_kit("_TST-HL4")
		so = self._make_order(ctx, qty=3)
		ctx["contract"].db_set("contract_status", "Fulfilled")

		first = link_historical_sales_orders(ctx["contract"].name, [so.name])
		second = link_historical_sales_orders(ctx["contract"].name, [so.name])
		self.assertEqual(first["total"], 1)
		self.assertEqual(second["total"], 0)

	def test_unrelated_sales_order_is_blocked(self):
		ctx = make_contract_kit("_TST-HL5")
		other_item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_TST-HL5-OTHER",
				"item_group": "Products",
				"is_stock_item": 1,
				"stock_uom": "Nos",
			}
		).insert()
		so = self._make_order(ctx, qty=1, item_code=other_item.name)

		with self.assertRaises(frappe.ValidationError):
			link_historical_sales_orders(ctx["contract"].name, [so.name])

	def test_cpt_free_issue_detection_and_link(self):
		ctx = make_contract_kit("_TST-HL6", contract_type="CPT", price_per_test=600)
		so = self._make_order(ctx, qty=2, rate=0)
		si = self._make_invoice(ctx, qty=2, rate=0, sales_order=so)

		rows = get_linkable_sales_orders(ctx["contract"].name)
		candidate = next(row for row in rows if row["name"] == so.name)
		self.assertEqual(candidate["suggested_type"], "Contract Free Issue")

		result = link_historical_sales_orders(ctx["contract"].name, [so.name])
		self.assertEqual(result["sales_orders"], 1)
		self.assertEqual(result["sales_invoices"], 1)
		si.reload()
		self.assertEqual(si.custom_counts_toward_recovery, 0)

	def test_other_company_sales_order_is_not_a_candidate(self):
		ctx = make_contract_kit("_TST-HL9")
		so = self._make_order(ctx, qty=1)
		frappe.db.set_value("Sales Order", so.name, "company", "OTHER COMPANY")

		rows = get_linkable_sales_orders(ctx["contract"].name)
		self.assertNotIn(so.name, {row["name"] for row in rows})

		with self.assertRaises(frappe.ValidationError):
			link_historical_sales_orders(ctx["contract"].name, [so.name])

	def test_candidate_search_requires_sales_order_read(self):
		ctx = make_contract_kit("_TST-HL10")
		so = self._make_order(ctx, qty=1)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"hist-{frappe.generate_hash(length=6)}@example.com",
				"first_name": "Historical Link Test",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		user.add_roles("Placement Manager")
		frappe.set_user(user.name)
		try:
			rows = get_linkable_sales_orders(ctx["contract"].name)
		finally:
			frappe.set_user("Administrator")
		self.assertNotIn(so.name, {row["name"] for row in rows})

	def test_chain_document_linked_to_other_contract_blocks_sales_order(self):
		ctx = make_contract_kit("_TST-HL7")
		other = make_contract_kit("_TST-HL8")
		so = self._make_order(ctx, qty=1)
		si = self._make_invoice(ctx, qty=1, sales_order=so)
		frappe.db.set_value(
			"Sales Invoice", si.name, "custom_instrument_placement_contract", other["contract"].name
		)

		with self.assertRaises(frappe.ValidationError):
			link_historical_sales_orders(ctx["contract"].name, [so.name])
