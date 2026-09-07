# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""
Patch: migrate_expense_scope_rename
------------------------------------
Renames Expense.expense_scope value "Single Purchase Order" -> "Purchase Order".
Bulk after_migrate patch covering all docstatus. Idempotent.
"""

import frappe


def execute():
	frappe.logger().info("[migrate_expense_scope_rename] Starting...")

	updated = frappe.db.sql(
		"UPDATE `tabExpense` SET expense_scope='Purchase Order' WHERE expense_scope='Single Purchase Order'"
	)
	# MySQL cursor returns rowcount via modified rows; fallback query for logging
	count = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabExpense` WHERE expense_scope='Purchase Order'"
	)[0][0]
	frappe.logger().info(f"[migrate_expense_scope_rename] normalized legacy rows. total now with Purchase Order={count}")

	frappe.db.commit()
	frappe.logger().info("[migrate_expense_scope_rename] Done.")
