# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import today

from nbs_customization.controllers.check_clearing import (
	create_check_clearing_je,
	get_check_mop,
	stamp_check_cleared,
)


def validate_check_payment_entry(pe, method=None):
	"""Force cheque Payment Entries onto the direction-correct clearing account."""
	if pe.payment_type not in ("Receive", "Pay") or not pe.mode_of_payment:
		return
	mop = get_check_mop(pe.mode_of_payment)
	if not mop.get("is_check"):
		return
	expected = (
		mop.get("clearing_account_inward")
		if pe.payment_type == "Receive"
		else mop.get("clearing_account_outward")
	)
	if not expected:
		frappe.throw(
			_("Mode of Payment '{0}' is a cheque mode but has no {1} clearing account set.").format(
				pe.mode_of_payment, "inward" if pe.payment_type == "Receive" else "outward"
			)
		)
	pe.set("is_check", 1)
	bank_side = "paid_to" if pe.payment_type == "Receive" else "paid_from"
	if pe.get(bank_side) != expected:
		pe.set(bank_side, expected)
	if not pe.clearing_destination_account and mop.get("default_clearing_destination"):
		pe.clearing_destination_account = mop.get("default_clearing_destination")


@frappe.whitelist(methods=["POST"])
def mark_check_cleared(name: str, destination_account: str | None = None, clearing_date: str | None = None):
	"""Button-driven clearing of a cheque Payment Entry.

	The funds land in `destination_account` (Bank or Cash); defaults to the
	mode of payment default or the company default bank account.
	"""
	pe = frappe.get_doc("Payment Entry", name)
	if pe.docstatus != 1:
		frappe.throw(_("Only submitted Payment Entries can be marked cleared."))
	mop = get_check_mop(pe.mode_of_payment)
	if not mop.get("is_check"):
		frappe.throw(_("{0} is not a cheque Payment Entry.").format(pe.name))
	if pe.check_cleared or pe.check_returned:
		frappe.throw(_("{0} is already cleared or returned.").format(pe.name))

	chosen = destination_account or pe.clearing_destination_account or mop.get("default_clearing_destination")
	if not chosen:
		chosen = frappe.get_cached_value("Company", pe.company, "default_bank_account")
	clear_date = clearing_date or today()

	je_name = create_check_clearing_je(pe, chosen, clear_date)
	rows = stamp_check_cleared(pe, je_name, clear_date, "Button", chosen)
	if rows != 1:
		# lost a race with another clear; undo the JE just created
		frappe.get_doc("Journal Entry", je_name).cancel()
		frappe.throw(_("{0} was already cleared.").format(pe.name))
	return {"journal_entry": je_name, "cleared": True}


@frappe.whitelist(methods=["POST"])
def mark_check_returned(name: str):
	"""A cheque bounced/returned.

	Reverses any prior clearing JE, then cancels the Payment Entry itself so the
	native cancel flow re-opens invoice allocations and reverses the GL.
	"""
	pe = frappe.get_doc("Payment Entry", name)
	if pe.docstatus != 1:
		frappe.throw(_("Only submitted Payment Entries can be marked returned."))
	if pe.check_returned:
		frappe.throw(_("{0} is already marked returned.").format(pe.name))

	if pe.clearing_journal_entry:
		# Break the circular PE <-> JE link first, otherwise Frappe blocks the
		# clearing Journal Entry from being cancelled (the submitted Payment
		# Entry points back at it via `clearing_journal_entry`).
		frappe.db.set_value("Payment Entry", pe.name, "clearing_journal_entry", None, update_modified=False)
		clearing_je = frappe.get_doc("Journal Entry", pe.clearing_journal_entry)
		if clearing_je.docstatus == 1:
			clearing_je.cancel()

	pe.cancel()
	frappe.db.set_value(
		"Payment Entry",
		pe.name,
		{
			"check_returned": 1,
			"check_return_date": today(),
			"check_cleared": 0,
			"check_clearing_date": None,
			"check_cleared_source": None,
			"clearing_destination_account": None,
			"clearance_date": None,
		},
	)
	return {"returned": True}
