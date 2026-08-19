import frappe
from frappe import _
from frappe.utils import flt, formatdate

from nbs_customization.nbs_customization.report.daily_income_and_expense.daily_income_and_expense import (
	get_cash_bank_balances,
	get_expenses,
	get_income,
)


@frappe.whitelist()
def get_data(company=None, report_date=None):
	company = company or frappe.defaults.get_user_default("Company")
	if not company or not report_date:
		frappe.throw(_("Company and Date are required."))

	company_currency = frappe.get_cached_value("Company", company, "default_currency")

	accounts, cash_bank_total = get_cash_bank_balances(company, report_date)
	income_detail = get_income(company, report_date)
	expense_detail = get_expenses(company, report_date)

	for row in income_detail:
		row.setdefault("type", row["voucher_type"])
	for row in expense_detail:
		row.setdefault("type", row["voucher_type"])

	total_income = sum(flt(row["amount"]) for row in income_detail)
	total_expense = sum(flt(row["amount"]) for row in expense_detail)

	return {
		"company": company,
		"report_date": report_date,
		"date_label": formatdate(report_date),
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
