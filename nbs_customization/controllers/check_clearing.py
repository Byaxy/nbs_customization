# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def get_check_mop(mode_of_payment):
	"""Return cheque-mode configuration for a Mode of Payment, or an empty dict."""
	if not mode_of_payment:
		return {}
	return (
		frappe.db.get_value(
			"Mode of Payment",
			mode_of_payment,
			[
				"is_check",
				"clearing_account_inward",
				"clearing_account_outward",
				"default_clearing_destination",
			],
			as_dict=1,
		)
		or {}
	)


def get_clearing_account(pe, mop):
	"""The clearing account a cheque Payment Entry posts against, by direction."""
	if pe.payment_type == "Receive":
		return pe.paid_to or mop.get("clearing_account_inward")
	return pe.paid_from or mop.get("clearing_account_outward")


def validate_single_currency(pe):
	"""v1 supports cheque clearing in company currency only."""
	company_currency = frappe.get_cached_value("Company", pe.company, "default_currency")
	if pe.paid_from_account_currency != company_currency or pe.paid_to_account_currency != company_currency:
		frappe.throw(
			_(
				"Cheque clearing is only supported in company currency ({0}) for now. "
				"Payment Entry {1} is in a foreign currency."
			).format(company_currency, pe.name)
		)


def validate_destination_account(destination_account, company):
	"""Destination must be a Bank or Cash account of the same company."""
	if not destination_account:
		frappe.throw(_("Clearing destination account is required."))
	details = frappe.get_cached_value("Account", destination_account, ["company", "account_type"], as_dict=1)
	if not details or details.company != company:
		frappe.throw(
			_("Clearing destination '{0}' is not an account of company '{1}'.").format(
				destination_account, company
			)
		)
	if details.account_type not in ("Bank", "Cash"):
		frappe.throw(
			_("Clearing destination '{0}' must be a Bank or Cash account, got type '{1}'.").format(
				destination_account, details.account_type
			)
		)


def create_check_clearing_je(pe, destination_account, clearing_date):
	"""
	Create and submit the clearing Journal Entry for a cheque Payment Entry.

	Receive: Dr <destination> / Cr <clearing account>
	Pay:     Dr <clearing account> / Cr <destination>

	Idempotency (avoiding double clear) is enforced by the caller through the
	`stamp_check_cleared` conditional update.
	"""
	validate_single_currency(pe)
	validate_destination_account(destination_account, pe.company)
	mop = get_check_mop(pe.mode_of_payment)
	clearing_account = get_clearing_account(pe, mop)
	if not clearing_account:
		frappe.throw(_("No clearing account configured for cheque Payment Entry {0}.").format(pe.name))

	amount = pe.paid_amount
	dimensions = {"cost_center": pe.cost_center, "project": pe.project}

	is_bank_entry = bool(pe.reference_no and pe.reference_date)
	je = frappe.get_doc(
		doctype="Journal Entry",
		voucher_type="Bank Entry" if is_bank_entry else "Journal Entry",
		company=pe.company,
		posting_date=clearing_date,
		user_remark=_("Cheque clearing against {0}").format(pe.name),
	)
	if is_bank_entry:
		je.cheque_no = pe.reference_no
		je.cheque_date = pe.reference_date

	if pe.payment_type == "Receive":
		je.append(
			"accounts",
			{
				"account": destination_account,
				"debit_in_account_currency": amount,
				"reference_type": "Payment Entry",
				"reference_name": pe.name,
				**dimensions,
			},
		)
		je.append(
			"accounts",
			{
				"account": clearing_account,
				"credit_in_account_currency": amount,
				"reference_type": "Payment Entry",
				"reference_name": pe.name,
				**dimensions,
			},
		)
	else:
		je.append(
			"accounts",
			{
				"account": clearing_account,
				"debit_in_account_currency": amount,
				"reference_type": "Payment Entry",
				"reference_name": pe.name,
				**dimensions,
			},
		)
		je.append(
			"accounts",
			{
				"account": destination_account,
				"credit_in_account_currency": amount,
				"reference_type": "Payment Entry",
				"reference_name": pe.name,
				**dimensions,
			},
		)

	je.insert(ignore_permissions=True)
	je.submit()
	return je.name


def stamp_check_cleared(pe, je_name, clearing_date, source, destination_account):
	"""Write Payment Entry flags after a clearing entry.

	Uses a conditional UPDATE so only one racing request can flip `check_cleared`
	0 -> 1. Returns the number of affected rows (1 = we own the clear).
	"""
	clearance_date = clearing_date if _is_bank_account(destination_account) else None
	frappe.db.sql(
		"""
		update `tabPayment Entry`
		set is_check = %s,
			check_cleared = 1,
			check_clearing_date = %s,
			check_cleared_source = %s,
			clearing_destination_account = %s,
			clearing_journal_entry = %s,
			clearance_date = %s
		where name = %s and docstatus = 1 and ifnull(check_cleared, 0) = 0
		""",
		(
			pe.is_check or 1,
			clearing_date,
			source,
			destination_account,
			je_name,
			clearance_date,
			pe.name,
		),
	)
	cursor = getattr(frappe.db, "_cursor", None)
	return (cursor.rowcount if cursor else 0) or 0


def _is_bank_account(account):
	return frappe.get_cached_value("Account", account, "account_type") == "Bank"
