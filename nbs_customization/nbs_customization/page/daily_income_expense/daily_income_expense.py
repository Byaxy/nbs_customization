import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate

from nbs_customization.nbs_customization.report.daily_income_and_expense.daily_income_and_expense import (
	get_cash_bank_balances,
	get_expenses,
	get_income,
)


def _resolve_dates(from_date=None, to_date=None, report_date=None):
	start = from_date or report_date
	end = to_date or report_date
	return start, end


@frappe.whitelist()
def get_data(
	company=None, from_date=None, to_date=None, report_date=None, income_only=None, expense_only=None
):
	company = company or frappe.defaults.get_user_default("Company")
	start, end = _resolve_dates(from_date, to_date, report_date)
	if not company or not start or not end:
		frappe.throw(_("Company, From Date and To Date are required."))
	if getdate(start) > getdate(end):
		frappe.throw(_("From Date cannot be after To Date."))

	# Both checked -> show both
	income_only = bool(int(income_only) if str(income_only).isdigit() else income_only)
	expense_only = bool(int(expense_only) if str(expense_only).isdigit() else expense_only)
	if income_only and expense_only:
		income_only = False
		expense_only = False

	company_currency = frappe.get_cached_value("Company", company, "default_currency")

	accounts, cash_bank_total = get_cash_bank_balances(company, start, end)

	# Income/Expenses conditional but cash always shown
	show_income = not expense_only
	show_expense = not income_only
	if income_only and expense_only:
		show_income = True
		show_expense = True

	if show_income:
		income_detail = get_income(company, start, end)
	else:
		income_detail = []
	if show_expense:
		expense_detail = get_expenses(company, start, end)
	else:
		expense_detail = []

	for row in income_detail:
		row.setdefault("type", row["voucher_type"])
	for row in expense_detail:
		row.setdefault("type", row["voucher_type"])

	total_income = sum(flt(row["amount"]) for row in income_detail)
	total_expense = sum(flt(row["amount"]) for row in expense_detail)

	if getdate(start) == getdate(end):
		date_label = formatdate(start)
	else:
		date_label = f"{formatdate(start)} to {formatdate(end)}"

	return {
		"company": company,
		"from_date": start,
		"to_date": end,
		"report_date": end,
		"date_label": date_label,
		"currency": company_currency,
		"accounts": [_account_card(row) for row in accounts],
		"cash_bank_total": {
			"brought_forward": flt(cash_bank_total["brought_forward"]),
			"day_movement": flt(cash_bank_total["day_movement"]),
			"carried_forward": flt(cash_bank_total["carried_forward"]),
		},
		"income": {
			"rows": income_detail,
			"total": flt(total_income),
		},
		"expenses": {
			"rows": expense_detail,
			"total": flt(total_expense),
		},
		"net": flt(total_income - total_expense),
	}


def _account_card(row):
	return {
		"account": row.account,
		"currency": row.account_currency,
		"brought_forward": flt(row["brought_forward"]),
		"day_movement": flt(row["day_movement"]),
		"carried_forward": flt(row["carried_forward"]),
	}
