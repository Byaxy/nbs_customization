# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns(bool(filters.get("include_cleared")))
	data = build_data(filters)
	return columns, data


def get_columns(include_cleared):
	columns = [
		{
			"fieldname": "name",
			"label": _("Payment Entry"),
			"fieldtype": "Link",
			"options": "Payment Entry",
			"width": 150,
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
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 150,
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
			"fieldname": "posting_date",
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"width": 90,
		},
		{
			"fieldname": "payment_type",
			"label": _("Payment Type"),
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
			"fieldtype": "Currency",
			"width": 70,
		},
		{
			"fieldname": "clearing_account",
			"label": _("Clearing Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 200,
		},
		{
			"fieldname": "days_outstanding",
			"label": _("Days Outstanding"),
			"fieldtype": "Int",
			"width": 120,
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
				"fieldname": "check_cleared_source",
				"label": _("Cleared Source"),
				"fieldtype": "Data",
				"width": 110,
			},
		]
	return columns


def build_data(filters):
	include_cleared = bool(filters.get("include_cleared"))
	conditions = ["docstatus = 1", "ifnull(is_check, 0) = 1", "ifnull(check_returned, 0) = 0"]
	if filters.get("company"):
		conditions.append("company = %s")
	if not include_cleared:
		conditions.append("ifnull(check_cleared, 0) = 0")

	query = """
		select name, party_type, party, reference_no, reference_date, posting_date,
			payment_type, paid_amount as amount, paid_from_account_currency,
			paid_to_account_currency,
			paid_to, paid_from, check_cleared, check_clearing_date, check_cleared_source
		from `tabPayment Entry`
		where {conditions}
		order by posting_date
	""".format(conditions=" and ".join(conditions))

	params = [filters.company] if filters.get("company") else None
	data = frappe.db.sql(query, params, as_dict=1)

	today = getdate()
	for row in data:
		row["currency"] = (
			row.paid_to_account_currency if row.payment_type == "Receive" else row.paid_from_account_currency
		)
		row["clearing_account"] = row.paid_to if row.payment_type == "Receive" else row.paid_from
		row["days_outstanding"] = (today - getdate(row.posting_date)).days if not row.check_cleared else 0
		row.pop("paid_from_account_currency", None)
		row.pop("paid_to_account_currency", None)
	return data
