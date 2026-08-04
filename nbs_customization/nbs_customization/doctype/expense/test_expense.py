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
			doc.expense_account = self.EXPENSE_ACCOUNT
			doc.insert(ignore_permissions=True)
		return "Test Expense Category"

	def _base_expense(self, **kwargs):
		args = dict(
			company=self.COMPANY,
			expense_date=today(),
			reference_date=today(),
			amount=100,
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
