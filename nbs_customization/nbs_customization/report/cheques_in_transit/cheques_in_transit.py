# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.desk.reportview import build_match_conditions
from frappe.utils import getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	columns = get_columns(bool(filters.get("include_cleared")), bool(filters.get("include_returned")))
	data = build_data(filters)
	return columns, data


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is required"))
	if filters.get("from_date") and filters.get("to_date"):
		if getdate(filters.from_date) > getdate(filters.to_date):
			frappe.throw(_("From Date cannot be after To Date"))


def get_columns(include_cleared, include_returned):
	columns = [
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Document"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 150,
		},
		{
			"fieldname": "source_doctype",
			"label": _("Source"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "posting_date",
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"width": 90,
		},
		{
			"fieldname": "reference_no",
			"label": _("Cheque No"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "reference_date",
			"label": _("Cheque Date"),
			"fieldtype": "Date",
			"width": 90,
		},
		{
			"fieldname": "party_type",
			"label": _("Party Type"),
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"fieldname": "party",
			"label": _("Party"),
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"fieldname": "clearing_account",
			"label": _("Clearing Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 200,
		},
		{
			"fieldname": "direction",
			"label": _("Direction"),
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"fieldname": "amount",
			"label": _("Amount"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 110,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Data",
			"width": 70,
		},
		{
			"fieldname": "days_outstanding",
			"label": _("Days Outstanding"),
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"fieldname": "clearing_destination_account",
			"label": _("Clearing Destination"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 180,
		},
		{
			"fieldname": "clearing_journal_entry",
			"label": _("Clearing JE"),
			"fieldtype": "Link",
			"options": "Journal Entry",
			"width": 150,
		},
	]
	if include_cleared:
		columns += [
			{
				"fieldname": "check_cleared",
				"label": _("Cleared"),
				"fieldtype": "Check",
				"width": 70,
			},
			{
				"fieldname": "check_clearing_date",
				"label": _("Clearing Date"),
				"fieldtype": "Date",
				"width": 90,
			},
			{
				"fieldname": "clearance_date",
				"label": _("Clearance Date"),
				"fieldtype": "Date",
				"width": 90,
			},
			{
				"fieldname": "check_cleared_source",
				"label": _("Cleared Source"),
				"fieldtype": "Data",
				"width": 110,
			},
		]
	if include_returned:
		columns += [
			{
				"fieldname": "check_returned",
				"label": _("Returned"),
				"fieldtype": "Check",
				"width": 70,
			},
			{
				"fieldname": "check_return_date",
				"label": _("Return Date"),
				"fieldtype": "Date",
				"width": 90,
			},
		]
	return columns


def _get_clearing_accounts(filters):
	# If user filtered specific clearing account(s), use them
	accounts = filters.get("account")
	if accounts:
		# MultiSelectList sends JSON string
		if isinstance(accounts, str):
			try:
				parsed = json.loads(accounts)
				if isinstance(parsed, list):
					accounts = parsed
				else:
					accounts = [accounts]
			except Exception:
				accounts = [accounts]
		if isinstance(accounts, list) and accounts:
			# filter empty strings
			accounts = [a for a in accounts if a]
			if accounts:
				return accounts
	# Otherwise fetch all clearing accounts for Check MOPs
	rows = frappe.db.get_all(
		"Mode of Payment",
		filters={"is_check": 1},
		fields=["clearing_account_inward", "clearing_account_outward"],
	)
	clearing = set()
	for r in rows:
		if r.get("clearing_account_inward"):
			clearing.add(r.clearing_account_inward)
		if r.get("clearing_account_outward"):
			clearing.add(r.clearing_account_outward)
	# Fallback via setup helper per company if MOP not yet configured
	if not clearing and filters.get("company"):
		try:
			from nbs_customization.setup import _account_for

			for name in ("Cheques in Transit - Inward", "Cheques in Transit - Outward"):
				acc = _account_for(filters.company, name)
				if acc:
					clearing.add(acc)
		except Exception:
			pass
	return sorted(clearing)


def _has_expense_check():
	try:
		return frappe.db.has_column("Expense", "is_check")
	except Exception:
		return False


def _has_commission_check():
	try:
		return frappe.db.has_column("Commission Payout", "is_check")
	except Exception:
		return False


def build_data(filters):
	include_cleared = bool(filters.get("include_cleared"))
	include_returned = bool(filters.get("include_returned"))
	clearing_accounts = _get_clearing_accounts(filters)

	if not clearing_accounts:
		return []

	# Build GL query params
	conditions = ["gle.is_cancelled = 0", "gle.company = %(company)s"]
	params = {"company": filters.company}

	if filters.get("from_date"):
		conditions.append("gle.posting_date >= %(from_date)s")
		params["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("gle.posting_date <= %(to_date)s")
		params["to_date"] = filters.to_date

	# Account filter — use IN with placeholders
	conditions.append("gle.account IN %(clearing_accounts)s")
	params["clearing_accounts"] = tuple(clearing_accounts)

	# Match conditions for permission
	try:
		match_cond = build_match_conditions("GL Entry")
		if match_cond:
			conditions.append(f"({match_cond})")
	except Exception:
		pass

	# Coalesce fields: prefer PE, then Expense, then Commission Payout
	# Use LEFT JOINs — vouchers may be PE or JE (for Expense/Commission)
	query = """
		SELECT
			gle.voucher_type,
			gle.voucher_no,
			gle.posting_date,
			gle.account AS clearing_account,
			gle.debit_in_account_currency,
			gle.credit_in_account_currency,
			gle.debit,
			gle.credit,
			gle.account_currency AS currency,
			gle.party_type AS gl_party_type,
			gle.party AS gl_party,
			gle.against AS gl_against,
			COALESCE(pe.reference_no, exp.reference_no, cp.reference_no) AS reference_no,
			COALESCE(pe.reference_date, exp.reference_date, cp.reference_date) AS reference_date,
			COALESCE(pe.party_type, exp_payee.party_type, cp_party.party_type) AS party_type,
			COALESCE(pe.party, exp.payee, cp.sales_person, gle.party) AS party,
			COALESCE(pe.payment_type, 'Pay') AS payment_type,
			COALESCE(pe.is_check, exp.is_check, cp.is_check, 0) AS is_check,
			COALESCE(pe.check_cleared, exp.check_cleared, cp.check_cleared, 0) AS check_cleared,
			COALESCE(pe.check_returned, exp.check_returned, cp.check_returned, 0) AS check_returned,
			COALESCE(pe.check_clearing_date, exp.check_clearing_date, cp.check_clearing_date) AS check_clearing_date,
			COALESCE(pe.check_return_date, exp.check_return_date, cp.check_return_date) AS check_return_date,
			COALESCE(pe.clearance_date, exp.clearance_date, cp.clearance_date) AS clearance_date,
			COALESCE(pe.check_cleared_source, exp.check_cleared_source, cp.check_cleared_source) AS check_cleared_source,
			COALESCE(pe.clearing_destination_account, exp.clearing_destination_account, cp.clearing_destination_account) AS clearing_destination_account,
			COALESCE(pe.clearing_journal_entry, exp.clearing_journal_entry, cp.clearing_journal_entry) AS clearing_journal_entry,
			pe.name AS pe_name,
			exp.name AS exp_name,
			cp.name AS cp_name
		FROM `tabGL Entry` gle
		LEFT JOIN `tabPayment Entry` pe ON pe.name = gle.voucher_no AND gle.voucher_type = 'Payment Entry'
		LEFT JOIN `tabExpense` exp ON exp.journal_entry = gle.voucher_no AND gle.voucher_type = 'Journal Entry'
		LEFT JOIN (
			SELECT name, payee, 'Payee' AS party_type, reference_no, reference_date, is_check, check_cleared, check_returned, check_clearing_date, check_return_date, clearance_date, check_cleared_source, clearing_destination_account, clearing_journal_entry, journal_entry
			FROM `tabExpense`
		) exp_payee ON exp_payee.journal_entry = gle.voucher_no
		LEFT JOIN `tabCommission Payout` cp ON cp.journal_entry = gle.voucher_no AND gle.voucher_type = 'Journal Entry'
		LEFT JOIN (SELECT name, sales_person, 'Sales Person' AS party_type, reference_no, reference_date, is_check, check_cleared, check_returned, check_clearing_date, check_return_date, clearance_date, check_cleared_source, clearing_destination_account, clearing_journal_entry, journal_entry FROM `tabCommission Payout`) cp_party ON cp_party.journal_entry = gle.voucher_no
		WHERE {conditions}
		ORDER BY gle.posting_date ASC, gle.voucher_no ASC
	""".format(conditions=" AND ".join(conditions))

	# has_column guard: if Expense/Commission Payout missing cheque columns, the COALESCE will error (unknown column).
	# Detect and fallback to simpler query without those columns.
	try:
		rows = frappe.db.sql(query, params, as_dict=1)
	except Exception as e:
		msg = str(e)
		if "Unknown column" in msg and ("cp." in msg or "exp." in msg):
			# Fallback without commission fields if not yet migrated
			has_cp = False
			query_fallback = query
			if not has_cp and "cp." in query:
				# Replace cp coalesce with NULL and drop cp joins for this run
				query_fallback = (
					query.replace(
						"COALESCE(pe.reference_no, exp.reference_no, cp.reference_no)",
						"COALESCE(pe.reference_no, exp.reference_no)",
					)
					.replace(
						"COALESCE(pe.reference_date, exp.reference_date, cp.reference_date)",
						"COALESCE(pe.reference_date, exp.reference_date)",
					)
					.replace(
						"LEFT JOIN `tabCommission Payout` cp ON cp.journal_entry = gle.voucher_no AND gle.voucher_type = 'Journal Entry'",
						"",
					)
					.replace(
						"LEFT JOIN (SELECT name, sales_person, 'Sales Person' AS party_type, reference_no, reference_date, is_check, check_cleared, check_returned, check_clearing_date, check_return_date, clearance_date, check_cleared_source, clearing_destination_account, clearing_journal_entry, journal_entry FROM `tabCommission Payout`) cp_party ON cp_party.journal_entry = gle.voucher_no",
						"",
					)
					.replace(
						"COALESCE(pe.party, exp.payee, cp.sales_person, gle.party)",
						"COALESCE(pe.party, exp.payee, gle.party)",
					)
					.replace(
						"COALESCE(pe.is_check, exp.is_check, cp.is_check, 0)",
						"COALESCE(pe.is_check, exp.is_check, 0)",
					)
					.replace(
						"COALESCE(pe.check_cleared, exp.check_cleared, cp.check_cleared, 0)",
						"COALESCE(pe.check_cleared, exp.check_cleared, 0)",
					)
					.replace(
						"COALESCE(pe.check_returned, exp.check_returned, cp.check_returned, 0)",
						"COALESCE(pe.check_returned, exp.check_returned, 0)",
					)
					.replace(
						"COALESCE(pe.check_clearing_date, exp.check_clearing_date, cp.check_clearing_date)",
						"COALESCE(pe.check_clearing_date, exp.check_clearing_date)",
					)
					.replace(
						"COALESCE(pe.check_return_date, exp.check_return_date, cp.check_return_date)",
						"COALESCE(pe.check_return_date, exp.check_return_date)",
					)
					.replace(
						"COALESCE(pe.clearance_date, exp.clearance_date, cp.clearance_date)",
						"COALESCE(pe.clearance_date, exp.clearance_date)",
					)
					.replace(
						"COALESCE(pe.check_cleared_source, exp.check_cleared_source, cp.check_cleared_source)",
						"COALESCE(pe.check_cleared_source, exp.check_cleared_source)",
					)
					.replace(
						"COALESCE(pe.clearing_destination_account, exp.clearing_destination_account, cp.clearing_destination_account)",
						"COALESCE(pe.clearing_destination_account, exp.clearing_destination_account)",
					)
					.replace(
						"COALESCE(pe.clearing_journal_entry, exp.clearing_journal_entry, cp.clearing_journal_entry)",
						"COALESCE(pe.clearing_journal_entry, exp.clearing_journal_entry)",
					)
					.replace(
						"COALESCE(pe.party_type, exp_payee.party_type, cp_party.party_type)",
						"COALESCE(pe.party_type, exp_payee.party_type)",
					)
				)
			try:
				rows = frappe.db.sql(query_fallback, params, as_dict=1)
			except Exception:
				# Ultimate fallback: PE only via GL (still GL-driven)
				rows = frappe.db.sql(
					"""
					SELECT gle.voucher_type, gle.voucher_no, gle.posting_date, gle.account AS clearing_account,
						gle.debit_in_account_currency, gle.credit_in_account_currency, gle.debit, gle.credit,
						gle.account_currency AS currency, gle.party_type AS gl_party_type, gle.party AS gl_party,
						pe.reference_no, pe.reference_date, pe.party_type, pe.party, pe.payment_type,
						pe.is_check, pe.check_cleared, pe.check_returned, pe.check_clearing_date, pe.check_return_date,
						pe.clearance_date, pe.check_cleared_source, pe.clearing_destination_account, pe.clearing_journal_entry
					FROM `tabGL Entry` gle
					LEFT JOIN `tabPayment Entry` pe ON pe.name = gle.voucher_no AND gle.voucher_type='Payment Entry'
					WHERE {conditions}
					ORDER BY gle.posting_date ASC, gle.voucher_no ASC
					""".format(conditions=" AND ".join(conditions)),
					params,
					as_dict=1,
				)
		else:
			raise

	# Determine direction from clearing account (Inward = Receive, Outward = Pay) + fallback payment_type
	# Also apply filters that couldn't be done in SQL
	today = getdate()
	data = []
	for r in rows:
		# Derive status
		is_returned = int(r.get("check_returned") or 0) == 1
		is_cleared = int(r.get("check_cleared") or 0) == 1
		if is_returned:
			status = "Returned"
		elif is_cleared:
			status = "Cleared"
		else:
			status = "Outstanding"

		# Filter include_cleared / include_returned
		if not include_cleared and is_cleared:
			continue
		if not include_returned and is_returned:
			continue

		# Payment type / direction filter
		direction = "Inward" if "Inward" in (r.get("clearing_account") or "") else "Outward"
		# Fallback if account naming deviated
		if r.get("payment_type") == "Receive":
			direction = "Inward"
		elif r.get("payment_type") == "Pay":
			direction = "Outward"

		if filters.get("payment_type"):
			want = filters.payment_type
			# Allow Inward/Outward or Receive/Pay
			if want == "Inward" and direction != "Inward":
				continue
			if want == "Outward" and direction != "Outward":
				continue
			if want in ("Receive", "Pay") and r.get("payment_type") != want:
				continue

		if filters.get("party_type") and r.get("party_type") != filters.party_type:
			continue
		if filters.get("party") and r.get("party") != filters.party:
			continue
		if filters.get("reference_no"):
			if (r.get("reference_no") or "").lower().find(filters.reference_no.lower()) == -1:
				continue

		# Amount: GL amount (positive), derive from debit - credit in account currency
		# For clearing legs, amount is debit if Inward? Actually GL for cheque: Receive Dr Inward, Pay Cr Outward.
		# Use debit_in_account_currency - credit_in_account_currency absolute, fallback to debit/credit.
		try:
			amt = (r.get("debit_in_account_currency") or 0) - (r.get("credit_in_account_currency") or 0)
			if not amt:
				amt = (r.get("debit") or 0) - (r.get("credit") or 0)
			amount = abs(amt)
		except Exception:
			amount = abs((r.get("debit") or 0) - (r.get("credit") or 0))

		if not amount:
			continue

		# Days outstanding
		try:
			posting = getdate(r.posting_date)
			days = (today - posting).days if not is_cleared else 0
		except Exception:
			days = 0

		if filters.get("days_outstanding_from") not in (None, "", 0):
			try:
				if days < int(filters.days_outstanding_from):
					continue
			except Exception:
				pass

		# Source doctype: voucher_type + which join matched
		if r.get("voucher_type") == "Payment Entry" and r.get("pe_name"):
			source = "Payment Entry"
			voucher_type = "Payment Entry"
			voucher_no = r.get("pe_name")
		elif r.get("exp_name"):
			source = "Expense"
			voucher_type = "Expense"
			voucher_no = r.get("exp_name")
			# For Expense Direct, voucher_no in GL is Journal Entry name; expose Expense name as document
		elif r.get("cp_name"):
			source = "Commission Payout"
			voucher_type = "Commission Payout"
			voucher_no = r.get("cp_name")
		else:
			# Fallback to GL voucher
			voucher_type = r.get("voucher_type")
			voucher_no = r.get("voucher_no")
			source = voucher_type

		# For Expense: still show Expense name as document, but keep Journal Entry reference in voucher_no for GL trace?
		# Keep document as source name for click-through.
		row = {
			"voucher_type": voucher_type,
			"source_doctype": source,
			"voucher_no": voucher_no,
			"name": voucher_no,
			"posting_date": r.get("posting_date"),
			"reference_no": r.get("reference_no"),
			"reference_date": r.get("reference_date"),
			"party_type": r.get("party_type"),
			"party": r.get("party"),
			"clearing_account": r.get("clearing_account"),
			"direction": direction,
			"payment_type": r.get("payment_type"),
			"amount": amount,
			"currency": r.get("currency"),
			"days_outstanding": days,
			"status": status,
			"check_cleared": 1 if is_cleared else 0,
			"check_returned": 1 if is_returned else 0,
			"check_clearing_date": r.get("check_clearing_date"),
			"check_return_date": r.get("check_return_date"),
			"clearance_date": r.get("clearance_date"),
			"check_cleared_source": r.get("check_cleared_source"),
			"clearing_destination_account": r.get("clearing_destination_account"),
			"clearing_journal_entry": r.get("clearing_journal_entry"),
		}
		data.append(row)

	# De-duplicate: one GL Entry per voucher line on clearing account — but a voucher may have 2 GL legs (one on clearing, one on expense/payable). We already filtered to clearing account only, so one per voucher ideally. Still dedupe by (voucher_type, voucher_no, clearing_account)
	seen = set()
	unique = []
	for r in data:
		key = (r["voucher_type"], r["voucher_no"], r["clearing_account"])
		if key in seen:
			continue
		seen.add(key)
		unique.append(r)

	unique.sort(key=lambda x: (x["posting_date"] or getdate("1900-01-01"), x["voucher_no"] or ""))
	return unique
