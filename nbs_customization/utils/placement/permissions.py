# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe

PLACEMENT_MANAGERS = ("System Manager", "Sales Manager")
FINANCE_MANAGERS = ("System Manager", "Accounts Manager")
STOCK_MANAGERS = ("System Manager", "Sales Manager", "Stock Manager")


def require_roles(*roles):
	"""Throw PermissionError unless the current user has one of the roles."""
	if not set(roles).intersection(frappe.get_roles()):
		frappe.throw(
			frappe._("You do not have permission to perform this action."),
			frappe.PermissionError,
		)


def require_contract_access(contract_name, ptype="read"):
	"""Check permission on the placement contract that authorizes a derived action."""
	frappe.has_permission(
		"Instrument Placement Contract",
		ptype,
		doc=contract_name,
		throw=True,
	)


def require_doc_access(doctype, name, ptype="read"):
	frappe.has_permission(doctype, ptype, doc=name, throw=True)


def is_placement_manager():
	return bool(set(PLACEMENT_MANAGERS).intersection(frappe.get_roles()))


def is_finance_manager():
	return bool(set(FINANCE_MANAGERS).intersection(frappe.get_roles()))


def is_stock_manager():
	return bool(set(STOCK_MANAGERS).intersection(frappe.get_roles()))
