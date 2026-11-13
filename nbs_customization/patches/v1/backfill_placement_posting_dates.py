# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe


def execute():
	_updates = (
		(
			"Instrument Pricing Worksheet",
			"posting_date = COALESCE(calculated_date, DATE(creation))",
			"IFNULL(posting_date, '') = ''",
		),
		(
			"Instrument Placement Contract",
			"posting_date = LEAST(CURDATE(), COALESCE(start_date, approval_date, DATE(creation)))",
			"IFNULL(posting_date, '') = ''",
		),
		(
			"Monthly Reconciliation",
			"posting_date = LEAST(CURDATE(), COALESCE(period_end, CURDATE()))",
			"IFNULL(posting_date, '') = ''",
		),
		(
			"Revenue Share Statement",
			"posting_date = LEAST(CURDATE(), COALESCE(period_end, CURDATE()))",
			"IFNULL(posting_date, '') = ''",
		),
	)
	for doctype, set_clause, where_clause in _updates:
		if frappe.db.table_exists(doctype):
			frappe.db.sql(f"UPDATE `tab{doctype}` SET {set_clause} WHERE {where_clause}")
