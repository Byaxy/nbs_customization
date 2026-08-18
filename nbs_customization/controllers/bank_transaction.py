# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import json

import frappe
from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import reconcile_vouchers
from frappe import _
from frappe.utils import flt

from nbs_customization.controllers.check_clearing import (
	create_check_clearing_je,
	stamp_check_cleared,
)


def _bank_gl_account(bank_transaction):
	return frappe.get_cached_value("Bank Account", bank_transaction.bank_account, "account")


def _transaction_amount(bank_transaction):
	return flt(
		bank_transaction.unallocated_amount or (bank_transaction.deposit - bank_transaction.withdrawal)
	)


@frappe.whitelist(methods=["GET"])
def get_uncleared_check_candidates(bank_transaction_name: str):
	"""Candidate uncleared cheque Payment Entries for a statement line, best match first."""
	bt = frappe.get_doc("Bank Transaction", bank_transaction_name)
	payment_type = "Receive" if bt.deposit > 0 else "Pay"
	amount = _transaction_amount(bt)

	rows = frappe.db.get_all(
		"Payment Entry",
		filters={
			"docstatus": 1,
			"payment_type": payment_type,
			"is_check": 1,
			"check_cleared": 0,
			"check_returned": 0,
		},
		fields=[
			"name",
			"party",
			"party_type",
			"paid_amount",
			"reference_no",
			"reference_date",
			"posting_date",
		],
	)

	candidates = []
	for row in rows:
		if abs(row.paid_amount - amount) > 0.01:
			continue
		rank = 0
		if row.reference_no and bt.reference_number and row.reference_no == bt.reference_number:
			rank += 10
		if bt.party and row.party == bt.party and row.party_type == bt.party_type:
			rank += 5
		candidates.append({**row, "rank": rank})
	return sorted(candidates, key=lambda r: r["rank"], reverse=True)


@frappe.whitelist(methods=["POST"])
def clear_check_from_bank_transaction(bank_transaction_name: str, payment_entry_name: str):
	"""Reconcile-time clear from a bank statement line.

	Creates the clearing JE into the statement's bank account, links it to the
	Bank Transaction (reconciling the line and stamping clearance), and flags
	the cheque Payment Entry as cleared.
	"""
	bt = frappe.get_doc("Bank Transaction", bank_transaction_name)
	pe = frappe.get_doc("Payment Entry", payment_entry_name)
	if pe.check_cleared or pe.check_returned:
		frappe.throw(_("{0} is already cleared or returned.").format(pe.name))
	if _transaction_amount(bt) <= 0:
		frappe.throw(_("Bank Transaction {0} has nothing left to reconcile.").format(bt.name))

	destination_account = _bank_gl_account(bt)
	je_name = create_check_clearing_je(pe, destination_account, bt.date)

	rows = stamp_check_cleared(pe, je_name, bt.date, "Bank Statement", destination_account)
	if rows != 1:
		frappe.get_doc("Journal Entry", je_name).cancel()
		frappe.throw(_("{0} was already cleared.").format(pe.name))

	reconcile_vouchers(
		bank_transaction_name,
		json.dumps(
			[
				{
					"payment_doctype": "Journal Entry",
					"payment_name": je_name,
					"amount": _transaction_amount(bt),
				}
			]
		),
		is_new_voucher=True,
	)
	return {"journal_entry": je_name, "bank_transaction": bt.name, "cleared": True}


def clear_check_vouchers_for_period(bank_account: str, from_date: str, to_date: str):
	"""Batch clear every unreconciled statement line whose reference number
	matches an uncleared cheque Payment Entry. Used at month-end."""
	bt_names = frappe.db.get_all(
		"Bank Transaction",
		filters={
			"bank_account": bank_account,
			"date": ["between", [from_date, to_date]],
			"docstatus": 1,
			"unallocated_amount": [">", 0],
		},
		pluck="name",
	)
	cleared = []
	for bt_name in bt_names:
		bt = frappe.get_doc("Bank Transaction", bt_name)
		if not bt.reference_number:
			continue
		pe_name = frappe.db.get_value(
			"Payment Entry",
			{
				"reference_no": bt.reference_number,
				"docstatus": 1,
				"is_check": 1,
				"check_cleared": 0,
			},
			"name",
		)
		if not pe_name:
			continue
		try:
			cleared.append(clear_check_from_bank_transaction(bt_name, pe_name))
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Cheque clearing batch")
	return cleared
