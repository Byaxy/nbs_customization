# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = build_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "section",
			"label": _("Section"),
			"fieldtype": "Data",
			"width": 60,
		},
		{
			"fieldname": "account",
			"label": _("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 220,
		},
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Data",
			"width": 90,
			"hidden": 1,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher No"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 150,
		},
		{
			"fieldname": "type",
			"label": _("Type"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "party",
			"label": _("Party / Payee"),
			"fieldtype": "Data",
			"width": 170,
		},
		{
			"fieldname": "mode_of_payment",
			"label": _("Mode of Payment"),
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"fieldname": "linked_invoice",
			"label": _("Linked Invoice / Expense"),
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"fieldname": "posting_date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 90,
		},
		{
			"fieldname": "brought_forward",
			"label": _("Brought Forward"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "day_movement",
			"label": _("Day Movement"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "carried_forward",
			"label": _("Carried Forward"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Currency",
			"width": 80,
			"hidden": 1,
		},
	]


def _resolve_dates(filters):
	# Backward compat: report_date -> from_date = to_date = report_date
	start = filters.get("from_date") or filters.get("start_date") or filters.get("report_date")
	end = filters.get("to_date") or filters.get("end_date") or filters.get("report_date")
	return start, end


def validate_filters(filters):
	company = filters.get("company")
	start, end = _resolve_dates(filters)
	if not company or not start or not end:
		frappe.throw(_("Company, From Date and To Date are required."))
	if getdate(start) > getdate(end):
		frappe.throw(_("From Date cannot be after To Date."))
	filters.from_date = start
	filters.to_date = end
	filters.start_date = start
	filters.end_date = end


def build_data(filters):
	validate_filters(filters)
	company = filters.get("company")
	start_date = filters.get("from_date")
	end_date = filters.get("to_date")

	if getdate(start_date) == getdate(end_date):
		date_label = formatdate(start_date)
	else:
		date_label = f"{formatdate(start_date)} to {formatdate(end_date)}"
	company_currency = frappe.get_cached_value("Company", company, "default_currency")

	income_only = bool(filters.get("income_only"))
	expense_only = bool(filters.get("expense_only"))
	# Both checked -> show both (locked decision)
	if income_only and expense_only:
		income_only = False
		expense_only = False

	data = []

	# ------------------------------------------------------------------ #
	# Cash & Bank — always shown, capped at to_date (decision 1)         #
	# ------------------------------------------------------------------ #
	data.append(_section_row(_(f"CASH & BANK — {date_label}")))
	balance_rows, total = get_cash_bank_balances(company, start_date, end_date)
	for row in balance_rows:
		data.append(_balance_row(row))
	data.append(_balance_total_row(total, company_currency))

	# ------------------------------------------------------------------ #
	# Income (cash received)                                              #
	# ------------------------------------------------------------------ #
	show_income = not expense_only
	show_expense = not income_only
	# Both checked handled above (both False -> both True)

	if show_income:
		data.append(_section_row(_(f"INCOME — {date_label}")))
		income_detail = get_income(company, start_date, end_date)
		for row in income_detail:
			data.append(_pnl_detail_row(row))
		total_income = sum(flt(row["amount"]) for row in income_detail)
		data.append(_pnl_total_row("Total Income", total_income, company_currency))
	else:
		income_detail = []
		total_income = 0
		data.append(_section_row(_(f"INCOME — {date_label} (hidden)")))
		data.append(_pnl_total_row("Total Income", 0, company_currency))

	# ------------------------------------------------------------------ #
	# Expenses (cash paid)                                                #
	# ------------------------------------------------------------------ #
	if show_expense:
		data.append(_section_row(_(f"EXPENSES — {date_label}")))
		expense_detail = get_expenses(company, start_date, end_date)
		for row in expense_detail:
			data.append(_pnl_detail_row(row))
		total_expense = sum(flt(row["amount"]) for row in expense_detail)
		data.append(_pnl_total_row("Total Expenses", total_expense, company_currency))
	else:
		expense_detail = []
		total_expense = 0
		data.append(_section_row(_(f"EXPENSES — {date_label} (hidden)")))
		data.append(_pnl_total_row("Total Expenses", 0, company_currency))

	# ------------------------------------------------------------------ #
	# Net income / loss                                                   #
	# ------------------------------------------------------------------ #
	data.append(_section_row(_("NET INCOME (LOSS)")))
	data.append(_pnl_total_row("Net Income (Loss)", total_income - total_expense, company_currency))

	return data


# ------------------------------------------------------------------ #
# Data queries                                                         #
# ------------------------------------------------------------------ #


CASH_BANK_CONDITION = """
	acc.is_group = 0
	AND (
		acc.account_type IN ('Bank', 'Cash')
		OR EXISTS (
			SELECT 1 FROM `tabAccount` pg
			WHERE pg.name = acc.parent_account
				AND pg.is_group = 1
				AND pg.account_type IN ('Bank', 'Cash')
		)
	)
"""


def get_cash_bank_balances(company, start_date, end_date=None):
	# Backward compat: single report_date
	if end_date is None:
		end_date = start_date
	rows = frappe.db.sql(
		f"""
		SELECT
			gle.account,
			acc.account_currency,
			SUM(CASE WHEN gle.posting_date < %(start_date)s
				THEN gle.debit_in_account_currency - gle.credit_in_account_currency ELSE 0 END) AS brought_forward,
			SUM(CASE WHEN gle.posting_date BETWEEN %(start_date)s AND %(end_date)s
				THEN gle.debit_in_account_currency - gle.credit_in_account_currency ELSE 0 END) AS day_movement,
			SUM(CASE WHEN gle.posting_date < %(start_date)s
				THEN gle.debit - gle.credit ELSE 0 END) AS brought_forward_base,
			SUM(CASE WHEN gle.posting_date BETWEEN %(start_date)s AND %(end_date)s
				THEN gle.debit - gle.credit ELSE 0 END) AS day_movement_base
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.docstatus = 1
			AND gle.is_cancelled = 0
			AND gle.company = %(company)s
			AND gle.posting_date <= %(end_date)s
			AND {CASH_BANK_CONDITION}
		GROUP BY gle.account, acc.account_currency
		ORDER BY acc.account_currency, gle.account
		""",
		{"company": company, "start_date": start_date, "end_date": end_date},
		as_dict=True,
	)

	for row in rows:
		row["brought_forward"] = flt(row.brought_forward)
		row["day_movement"] = flt(row.day_movement)
		row["carried_forward"] = row["brought_forward"] + row["day_movement"]
		row["brought_forward_base"] = flt(row.brought_forward_base)
		row["day_movement_base"] = flt(row.day_movement_base)
		row["carried_forward_base"] = row["brought_forward_base"] + row["day_movement_base"]

	total = {
		"brought_forward": sum(row["brought_forward_base"] for row in rows),
		"day_movement": sum(row["day_movement_base"] for row in rows),
		"carried_forward": sum(row["carried_forward_base"] for row in rows),
	}

	return rows, total


def get_income(company, start_date, end_date=None):
	if end_date is None:
		end_date = start_date
	return frappe.db.sql(
		"""
		SELECT pe.name AS voucher_no, 'Payment Entry' AS voucher_type, pe.posting_date,
			pe.party_name AS party, pe.mode_of_payment, pe.base_paid_amount AS amount,
			GROUP_CONCAT(per.reference_name SEPARATOR ', ') AS linked_invoice
		FROM `tabPayment Entry` pe
		LEFT JOIN `tabPayment Entry Reference` per
			ON per.parent = pe.name AND per.reference_doctype = 'Sales Invoice'
		WHERE pe.docstatus = 1
			AND pe.company = %(company)s
			AND pe.posting_date BETWEEN %(start_date)s AND %(end_date)s
			AND pe.payment_type = 'Receive'
		GROUP BY pe.name
		ORDER BY pe.posting_date, pe.name
		""",
		{"company": company, "start_date": start_date, "end_date": end_date},
		as_dict=True,
	)


def get_expenses(company, start_date, end_date=None):
	if end_date is None:
		end_date = start_date
	rows = frappe.db.sql(
		"""
		SELECT pe.name AS voucher_no, 'Payment Entry' AS voucher_type, pe.posting_date,
			pe.party_name AS party, pe.mode_of_payment, pe.base_paid_amount AS amount,
			GROUP_CONCAT(per.reference_name SEPARATOR ', ') AS linked_invoice
		FROM `tabPayment Entry` pe
		LEFT JOIN `tabPayment Entry Reference` per
			ON per.parent = pe.name AND per.reference_doctype = 'Purchase Invoice'
		WHERE pe.docstatus = 1
			AND pe.company = %(company)s
			AND pe.posting_date BETWEEN %(start_date)s AND %(end_date)s
			AND pe.payment_type = 'Pay'
		GROUP BY pe.name
		ORDER BY pe.posting_date, pe.name
		""",
		{"company": company, "start_date": start_date, "end_date": end_date},
		as_dict=True,
	)

	je_rows = frappe.db.sql(
		"""
		SELECT je.name AS voucher_no, 'Journal Entry' AS voucher_type, je.posting_date,
			e.payee AS party, je.mode_of_payment, e.amount AS amount, e.name AS linked_invoice
		FROM `tabJournal Entry` je
		INNER JOIN `tabExpense` e ON e.journal_entry = je.name
		WHERE je.docstatus = 1
			AND je.company = %(company)s
			AND je.posting_date BETWEEN %(start_date)s AND %(end_date)s
		ORDER BY je.posting_date, je.name
		""",
		{"company": company, "start_date": start_date, "end_date": end_date},
		as_dict=True,
	)

	commission_rows = frappe.db.sql(
		"""
		SELECT je.name AS voucher_no, 'Journal Entry' AS voucher_type, je.posting_date,
			cp.sales_person AS party, cp.mode_of_payment, cp.amount_to_pay AS amount,
			cp.name AS linked_invoice, 'Commission Payout' AS type
		FROM `tabJournal Entry` je
		INNER JOIN `tabCommission Payout` cp ON cp.journal_entry = je.name
		WHERE je.docstatus = 1
			AND je.company = %(company)s
			AND je.posting_date BETWEEN %(start_date)s AND %(end_date)s
		ORDER BY je.posting_date, je.name
		""",
		{"company": company, "start_date": start_date, "end_date": end_date},
		as_dict=True,
	)

	return sorted(
		rows + je_rows + commission_rows,
		key=lambda row: (row.posting_date, row.voucher_no),
	)


# ------------------------------------------------------------------ #
# Row builders                                                        #
# ------------------------------------------------------------------ #


def _section_row(text):
	return {"section": text}


def _balance_row(row):
	return {
		"section": "",
		"account": row.account,
		"brought_forward": row["brought_forward"],
		"day_movement": row["day_movement"],
		"carried_forward": row["carried_forward"],
		"currency": row.account_currency,
	}


def _balance_total_row(total, currency):
	return {
		"section": "",
		"account": _("Total Cash & Bank"),
		"brought_forward": flt(total["brought_forward"]),
		"day_movement": flt(total["day_movement"]),
		"carried_forward": flt(total["carried_forward"]),
		"currency": currency,
	}


def _pnl_detail_row(row):
	return {
		"section": "",
		"voucher_type": row.voucher_type,
		"voucher_no": row.voucher_no,
		"type": row.get("type") or row.voucher_type,
		"party": row.get("party") or "",
		"mode_of_payment": row.get("mode_of_payment") or "",
		"linked_invoice": row.get("linked_invoice") or "",
		"posting_date": row.posting_date,
		"day_movement": flt(row["amount"]),
	}


def _pnl_total_row(label, amount, currency):
	return {
		"section": "",
		"account": _(label),
		"day_movement": flt(amount),
		"currency": currency,
	}
