# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

COMPANY = "_Test Company"


def _ensure_test_setup():
	"""Create the cheque clearing accounts for _Test Company and point the
	Check Mode of Payment at them. Runs inside the test transaction."""
	from nbs_customization.setup import _account_for, _ensure_check_clearing_setup

	_ensure_check_clearing_setup()
	mop = frappe.get_doc("Mode of Payment", "Check")
	mop.clearing_account_inward = _account_for(COMPANY, "Cheques in Transit - Inward")
	mop.clearing_account_outward = _account_for(COMPANY, "Cheques in Transit - Outward")
	mop.default_clearing_destination = None
	mop.flags.ignore_permissions = True
	mop.save()
	return mop


def _make_party(doctype, name):
	if not frappe.db.exists(doctype, name):
		field = "customer_name" if doctype == "Customer" else "supplier_name"
		frappe.get_doc({"doctype": doctype, field: name}).insert(ignore_if_duplicate=True)
	return name


def _make_check_pe(payment_type, amount=1000.0, reference_no=None, party=None):
	from erpnext.accounts.party import get_party_account

	party_type = "Customer" if payment_type == "Receive" else "Supplier"
	party = party or _make_party(
		party_type,
		"_Test Check Clearing " + party_type,
	)
	party_account = get_party_account(party_type, party, COMPANY)
	mop = frappe.get_doc("Mode of Payment", "Check")
	inward = mop.clearing_account_inward
	outward = mop.clearing_account_outward

	pe = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"payment_type": payment_type,
			"posting_date": today(),
			"company": COMPANY,
			"mode_of_payment": "Check",
			"party_type": party_type,
			"party": party,
			"paid_from": party_account if payment_type == "Receive" else outward,
			"paid_to": inward if payment_type == "Receive" else party_account,
			"paid_amount": amount,
			"received_amount": amount,
			"reference_no": reference_no,
			"reference_date": today(),
		}
	)
	pe.insert()
	pe.submit()
	return pe


def _account_balance(account, voucher_no=None):
	if not account or not frappe.db.exists("Account", account):
		return 0.0
	sql = """
		select ifnull(sum(debit) - sum(credit), 0)
		from `tabGL Entry`
		where account = %s and is_cancelled = 0
	"""
	params = [account]
	if voucher_no:
		sql += " and voucher_no = %s"
		params.append(voucher_no)
	return flt(frappe.db.sql(sql, params)[0][0])


class TestCheckClearing(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		_ensure_test_setup()

	def test_receive_check_forced_to_clearing_and_cleared_to_bank(self):
		pe = _make_check_pe("Receive")
		pe.reload()
		self.assertEqual(pe.is_check, 1)
		self.assertEqual(pe.paid_to, frappe.get_doc("Mode of Payment", "Check").clearing_account_inward)

		res = frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_cleared",
			name=pe.name,
			destination_account="_Test Bank - _TC",
		)
		self.assertTrue(res["cleared"])

		pe.reload()
		self.assertEqual(pe.check_cleared, 1)
		self.assertEqual(pe.clearing_journal_entry, res["journal_entry"])
		self.assertEqual(pe.check_cleared_source, "Button")
		self.assertEqual(str(pe.clearance_date), today())

		# bank +1000 (debit), clearing account nets back to zero
		self.assertEqual(_account_balance("_Test Bank - _TC", res["journal_entry"]), 1000)
		self.assertEqual(
			_account_balance(frappe.get_doc("Mode of Payment", "Check").clearing_account_inward),
			0,
		)

	def test_clear_to_cash_keeps_bank_clearance_blank(self):
		pe = _make_check_pe("Receive")
		res = frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_cleared",
			name=pe.name,
			destination_account="Cash - _TC",
		)
		pe.reload()
		self.assertEqual(pe.check_cleared, 1)
		self.assertFalse(pe.clearance_date)
		self.assertEqual(_account_balance("Cash - _TC", res["journal_entry"]), 1000)

	def test_pay_cheque_cleared_to_bank(self):
		pe = _make_check_pe("Pay")
		pe.reload()
		self.assertEqual(pe.is_check, 1)
		self.assertEqual(pe.paid_from, frappe.get_doc("Mode of Payment", "Check").clearing_account_outward)

		res = frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_cleared",
			name=pe.name,
			destination_account="_Test Bank - _TC",
		)
		pe.reload()
		self.assertEqual(pe.check_cleared, 1)
		# clearing account debited +1000, bank credited -1000
		self.assertEqual(
			_account_balance(frappe.get_doc("Mode of Payment", "Check").clearing_account_outward),
			0,
		)
		self.assertEqual(_account_balance("_Test Bank - _TC", res["journal_entry"]), -1000)

	def test_double_clear_raises(self):
		pe = _make_check_pe("Receive")
		frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_cleared",
			name=pe.name,
			destination_account="_Test Bank - _TC",
		)
		with self.assertRaises(frappe.ValidationError):
			frappe.call(
				"nbs_customization.controllers.payment_entry.mark_check_cleared",
				name=pe.name,
				destination_account="_Test Bank - _TC",
			)

	def test_destination_must_be_bank_or_cash(self):
		pe = _make_check_pe("Receive")
		with self.assertRaises(frappe.ValidationError):
			frappe.call(
				"nbs_customization.controllers.payment_entry.mark_check_cleared",
				name=pe.name,
				destination_account="Debtors - _TC",
			)

	def test_returned_check_cancels_pe_and_reverses_gl(self):
		pe = _make_check_pe("Receive", reference_no="RETURNED-001")
		res = frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_cleared",
			name=pe.name,
			destination_account="_Test Bank - _TC",
		)

		frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_returned",
			name=pe.name,
		)

		pe.reload()
		self.assertEqual(pe.docstatus, 2)
		self.assertEqual(pe.check_returned, 1)
		self.assertEqual(pe.check_cleared, 0)
		je = frappe.get_doc("Journal Entry", res["journal_entry"])
		self.assertEqual(je.docstatus, 2)
		self.assertEqual(
			_account_balance(frappe.get_doc("Mode of Payment", "Check").clearing_account_inward),
			0,
		)

	def test_returned_check_before_clear(self):
		pe = _make_check_pe("Receive")
		frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_returned",
			name=pe.name,
		)
		pe.reload()
		self.assertEqual(pe.docstatus, 2)
		self.assertEqual(pe.check_returned, 1)
		self.assertEqual(pe.check_cleared, 0)

	def test_candidates_and_bank_transaction_clear(self):
		uniq = frappe.generate_hash(length=6)

		bank_gl = frappe.get_doc(
			{
				"doctype": "Account",
				"company": COMPANY,
				"account_name": "_Test Bank Clearing " + uniq,
				"parent_account": "Current Assets - _TC",
				"account_type": "Bank",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)

		if not frappe.db.exists("Bank", "Citi Bank"):
			frappe.get_doc({"doctype": "Bank", "bank_name": "Citi Bank"}).insert(ignore_if_duplicate=True)
		bank_account = frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": "Checking " + uniq,
				"bank": "Citi Bank",
				"account": bank_gl.name,
			}
		).insert(ignore_if_duplicate=True)

		bt = frappe.get_doc(
			{
				"doctype": "Bank Transaction",
				"description": "cheque deposit",
				"date": today(),
				"deposit": 1000,
				"currency": "INR",
				"bank_account": bank_account.name,
				"reference_number": "CHQBT-" + uniq,
			}
		).insert()
		bt.submit()

		pe = _make_check_pe("Receive", reference_no="CHQBT-" + uniq)
		candidates = frappe.call(
			"nbs_customization.controllers.bank_transaction.get_uncleared_check_candidates",
			bank_transaction_name=bt.name,
		)
		self.assertTrue(any(c["name"] == pe.name for c in candidates))

		res = frappe.call(
			"nbs_customization.controllers.bank_transaction.clear_check_from_bank_transaction",
			bank_transaction_name=bt.name,
			payment_entry_name=pe.name,
		)
		bt.reload()
		pe.reload()
		self.assertEqual(flt(bt.unallocated_amount), 0)
		self.assertEqual(pe.check_cleared, 1)
		self.assertEqual(pe.check_cleared_source, "Bank Statement")
		self.assertEqual(pe.clearing_journal_entry, res["journal_entry"])
		self.assertEqual(_account_balance(bank_gl.name, res["journal_entry"]), 1000)

	def test_cheques_in_transit_report(self):
		from nbs_customization.nbs_customization.report.cheques_in_transit.cheques_in_transit import execute

		pe = _make_check_pe("Receive", reference_no="REPORT-001")
		_columns, data = execute(filters={"company": COMPANY})
		self.assertTrue(any(row["name"] == pe.name for row in data))

		frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_cleared",
			name=pe.name,
			destination_account="_Test Bank - _TC",
		)
		_columns, data = execute(filters={"company": COMPANY})
		self.assertFalse(any(row["name"] == pe.name for row in data))

		_columns, data = execute(filters={"company": COMPANY, "include_cleared": 1})
		row = next((r for r in data if r["name"] == pe.name), None)
		self.assertIsNotNone(row)
		self.assertEqual(row["check_cleared"], 1)

	def test_clearing_accounts_under_receivable_payable_groups(self):
		from nbs_customization.setup import _account_for

		inward = _account_for(COMPANY, "Cheques in Transit - Inward")
		outward = _account_for(COMPANY, "Cheques in Transit - Outward")
		self.assertEqual(
			frappe.db.get_value("Account", inward, "parent_account"), "Accounts Receivable - _TC"
		)
		self.assertEqual(frappe.db.get_value("Account", outward, "parent_account"), "Accounts Payable - _TC")
