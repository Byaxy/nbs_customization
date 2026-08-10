# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, today


class IntegrationTestExpense(IntegrationTestCase):
	COMPANY = "_Test Company"
	BANK = "_Test Bank - _TC"
	EQUITY = "Opening Balance Equity - _TC"
	EXPENSE_ACCOUNT = "Loyalty - _TC"

	def _credit_bank(self, amount=10000):
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.COMPANY
		je.posting_date = today()
		je.user_remark = "seed bank balance for Expense tests"
		je.append(
			"accounts",
			{
				"account": self.EQUITY,
				"debit_in_account_currency": amount,
				"credit_in_account_currency": 0,
			},
		)
		je.append(
			"accounts",
			{
				"account": self.BANK,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": amount,
			},
		)
		je.insert(ignore_permissions=True)
		je.submit()
		return je

	def _expense_category(self):
		if not frappe.db.exists("Expense Category", "Test Expense Category"):
			doc = frappe.new_doc("Expense Category")
			doc.name = "Test Expense Category"
			doc.category_name = "Test Expense Category"
			doc.expense_account = self.EXPENSE_ACCOUNT
			doc.insert(ignore_permissions=True)
		return "Test Expense Category"

	def _base_expense(self, **kwargs):
		args = dict(
			company=self.COMPANY,
			expense_date=today(),
			reference_date=today(),
			amount=100,
			expense_description="Test Expense",
			payee="Test Payee",
			expense_category=self._expense_category(),
			mode_of_payment="Wire Transfer",
			paid_from=self.BANK,
		)
		args.update(kwargs)
		doc = frappe.new_doc("Expense")
		doc.update(args)
		return doc

	def test_bank_reference_required(self):
		doc = self._base_expense(payment_type="Direct Payment", reference_no=None, reference_date=None)
		with self.assertRaises(frappe.ValidationError):
			doc.validate()

	def test_cash_does_not_require_reference(self):
		doc = self._base_expense(
			payment_type="Direct Payment",
			paid_from="_Test Cash - _TC",
			reference_no=None,
			reference_date=None,
		)
		doc.validate()

	def test_direct_payment_carries_reference_to_je(self):
		seeding_je = self._credit_bank()
		doc = self._base_expense(
			payment_type="Direct Payment", reference_no="CHK-0001", reference_date=today()
		)
		doc.insert()
		doc.submit()

		je = frappe.get_doc("Journal Entry", doc.journal_entry)
		self.assertEqual(je.cheque_no, "CHK-0001")
		self.assertEqual(getdate(je.cheque_date), getdate(doc.reference_date))
		self.assertEqual(je.mode_of_payment, "Wire Transfer")

		doc.cancel()
		je.reload()
		self.assertEqual(je.docstatus, 2)
		seeding_je.cancel()

	def test_against_pi_carries_reference_to_pe(self):
		from erpnext.accounts.doctype.purchase_invoice.test_purchase_invoice import (
			make_purchase_invoice,
		)

		seeding_je = self._credit_bank()
		pi = make_purchase_invoice()
		try:
			doc = self._base_expense(
				payment_type="Against Purchase Invoice",
				purchase_invoice=pi.name,
				reference_no="BANK-TRF-001",
				reference_date=today(),
			)
			doc.insert()
			doc.submit()

			pe = frappe.get_doc("Payment Entry", doc.payment_entry)
			self.assertEqual(pe.reference_no, "BANK-TRF-001")
			self.assertEqual(getdate(pe.reference_date), getdate(doc.reference_date))
			self.assertEqual(pe.mode_of_payment, "Wire Transfer")

			doc.cancel()
			pe.reload()
			self.assertEqual(pe.docstatus, 2)
		finally:
			seeding_je.cancel()
			pi.reload()
			if pi.docstatus == 1:
				pi.cancel()
			frappe.delete_doc("Purchase Invoice", pi.name, force=True)

	# ------------------------------------------------------------------ #
	# Accompanying expenses — Purchase Order scope helpers                #
	# ------------------------------------------------------------------ #

	VALUATION_ACCOUNT = "Expenses Included In Valuation - _TC"

	def _valuation_category(self):
		name = "Test Accompanying Expense Category"
		if not frappe.db.exists("Expense Category", name):
			doc = frappe.new_doc("Expense Category")
			doc.name = name
			doc.category_name = name
			doc.expense_account = self.VALUATION_ACCOUNT
			doc.is_accompanying_expense = 1
			doc.insert(ignore_permissions=True)
		return name

	def _make_po(self, qty=10):
		po = frappe.new_doc("Purchase Order")
		po.company = self.COMPANY
		po.supplier = "_Test Supplier"
		po.transaction_date = today()
		po.schedule_date = today()
		po.append(
			"items",
			{
				"item_code": "_Test Item",
				"schedule_date": today(),
				"qty": qty,
				"rate": 100,
				"warehouse": "_Test Warehouse - _TC",
				"cost_center": "Main - _TC",
			},
		)
		po.insert()
		po.submit()
		return po

	def _receive_po(self, po, qty):
		from erpnext.buying.doctype.purchase_order.purchase_order import (
			make_purchase_receipt,
		)

		pr = make_purchase_receipt(po.name)
		if pr.items:
			pr.items[0].qty = qty
			pr.items[0].received_qty = qty
		pr.insert()
		pr.submit()
		return pr

	def _accompanying_expense(self, **kwargs):
		args = dict(
			payment_type="Direct Payment",
			is_accompanying=1,
			expense_scope="Single Purchase Order",
			expense_category=self._valuation_category(),
			reference_no="CHK-0002",
		)
		args.update(kwargs)
		return self._base_expense(**args)

	def test_po_scope_requires_purchase_order(self):
		doc = self._accompanying_expense(linked_purchase_order=None)
		with self.assertRaises(frappe.ValidationError):
			doc.validate()

	def test_po_scope_requires_submitted_po(self):
		po = frappe.new_doc("Purchase Order")
		po.company = self.COMPANY
		po.supplier = "_Test Supplier"
		po.transaction_date = today()
		po.schedule_date = today()
		po.append(
			"items",
			{
				"item_code": "_Test Item",
				"schedule_date": today(),
				"qty": 5,
				"rate": 100,
				"warehouse": "_Test Warehouse - _TC",
				"cost_center": "Main - _TC",
			},
		)
		po.insert()  # draft — not submitted
		try:
			doc = self._accompanying_expense(linked_purchase_order=po.name)
			with self.assertRaises(frappe.ValidationError):
				doc.validate()
		finally:
			frappe.delete_doc("Purchase Order", po.name, force=True)

	def test_lcv_blocked_until_po_fully_received(self):
		from nbs_customization.nbs_customization.doctype.expense.expense import (
			make_landed_cost_voucher,
		)

		po = self._make_po(qty=10)
		seeding_je = self._credit_bank()
		doc = self._accompanying_expense(linked_purchase_order=po.name)
		doc.insert()
		doc.submit()
		try:
			with self.assertRaises(frappe.ValidationError):
				make_landed_cost_voucher(doc.name)
		finally:
			doc.cancel()
			seeding_je.cancel()
			po.cancel()
			frappe.delete_doc("Purchase Order", po.name, force=True)

	def test_lcv_created_with_all_prs_of_po(self):
		from nbs_customization.nbs_customization.doctype.expense.expense import (
			make_landed_cost_voucher,
		)

		po = self._make_po(qty=10)
		pr1 = self._receive_po(po, 4)
		pr2 = self._receive_po(po, 6)
		seeding_je = self._credit_bank()
		doc = self._accompanying_expense(linked_purchase_order=po.name, amount=100)
		doc.insert()
		doc.submit()
		lcv_name = None
		try:
			lcv_name = make_landed_cost_voucher(doc.name)
			lcv = frappe.get_doc("Landed Cost Voucher", lcv_name)
			self.assertEqual(len(lcv.purchase_receipts), 2)
			self.assertEqual(len(lcv.taxes), 1)
			self.assertEqual(lcv.distribute_charges_based_on, "Distribute Manually")
			self.assertEqual(lcv.custom_linked_purchase_order, po.name)
			doc.reload()
			self.assertEqual(doc.landed_cost_voucher, lcv_name)
		finally:
			if lcv_name and frappe.db.exists("Landed Cost Voucher", lcv_name):
				lcv = frappe.get_doc("Landed Cost Voucher", lcv_name)
				if lcv.docstatus == 1:
					lcv.cancel()
				frappe.delete_doc("Landed Cost Voucher", lcv_name, force=True)
			doc.cancel()
			seeding_je.cancel()
			pr2.cancel()
			pr1.cancel()
			frappe.delete_doc("Purchase Receipt", pr2.name, force=True)
			frappe.delete_doc("Purchase Receipt", pr1.name, force=True)
			po.reload()
			po.cancel()
			frappe.delete_doc("Purchase Order", po.name, force=True)

	def test_backfill_single_po_purchase_receipt(self):
		from nbs_customization.nbs_customization.backfill_expense_purchase_orders import (
			run as run_backfill,
		)

		po = self._make_po(qty=5)
		pr = self._receive_po(po, 5)
		doc = self._accompanying_expense(
			expense_scope="Single Purchase Order",
			linked_purchase_order=po.name,
			amount=100,
		)
		doc.insert()
		frappe.db.set_value(
			"Expense",
			doc.name,
			{
				"expense_scope": "Single Purchase Receipt",
				"linked_purchase": pr.name,
				"linked_purchase_order": None,
			},
		)
		doc.reload()
		try:
			run_backfill(dry_run=False, commit=False)
			doc.reload()
			self.assertEqual(doc.expense_scope, "Single Purchase Order")
			self.assertEqual(doc.linked_purchase_order, po.name)
		finally:
			frappe.delete_doc("Expense", doc.name, force=True)
			pr.cancel()
			frappe.delete_doc("Purchase Receipt", pr.name, force=True)
			po.reload()
			po.cancel()
			frappe.delete_doc("Purchase Order", po.name, force=True)

	def test_backfill_skips_multi_po_purchase_receipt(self):
		from nbs_customization.nbs_customization.backfill_expense_purchase_orders import (
			run as run_backfill,
		)

		po1 = self._make_po(qty=5)
		po2 = self._make_po(qty=5)

		pr = frappe.new_doc("Purchase Receipt")
		pr.company = self.COMPANY
		pr.supplier = "_Test Supplier"
		pr.posting_date = today()
		pr.set_posting_time = 1
		pr.append(
			"items",
			{
				"item_code": "_Test Item",
				"qty": 5,
				"received_qty": 5,
				"rate": 100,
				"warehouse": "_Test Warehouse - _TC",
				"cost_center": "Main - _TC",
				"purchase_order": po1.name,
				"purchase_order_item": po1.items[0].name,
			},
		)
		pr.append(
			"items",
			{
				"item_code": "_Test Item",
				"qty": 5,
				"received_qty": 5,
				"rate": 100,
				"warehouse": "_Test Warehouse - _TC",
				"cost_center": "Main - _TC",
				"purchase_order": po2.name,
				"purchase_order_item": po2.items[0].name,
			},
		)
		pr.insert()
		pr.submit()

		doc = self._accompanying_expense(
			expense_scope="Single Purchase Order",
			linked_purchase_order=po1.name,
			amount=100,
		)
		doc.insert()
		frappe.db.set_value(
			"Expense",
			doc.name,
			{
				"expense_scope": "Single Purchase Receipt",
				"linked_purchase": pr.name,
				"linked_purchase_order": None,
			},
		)
		doc.reload()
		try:
			run_backfill(dry_run=False, commit=False)
			doc.reload()
			self.assertEqual(doc.expense_scope, "Single Purchase Receipt")
			self.assertIsNone(doc.linked_purchase_order)
		finally:
			frappe.delete_doc("Expense", doc.name, force=True)
			pr.cancel()
			frappe.delete_doc("Purchase Receipt", pr.name, force=True)
			po1.reload()
			po2.reload()
			po1.cancel()
			po2.cancel()
			frappe.delete_doc("Purchase Order", po1.name, force=True)
			frappe.delete_doc("Purchase Order", po2.name, force=True)
