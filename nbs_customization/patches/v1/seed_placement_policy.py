# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe

ROLES = (
	("Placement Manager", 1),
	("Field Engineer", 1),
	("Placement Director", 1),
)


def execute():
	_ensure_roles()
	_ensure_settings()


def _ensure_roles():
	for role_name, desk_access in ROLES:
		if frappe.db.exists("Role", role_name):
			continue
		frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": desk_access}).insert(
			ignore_permissions=True
		)


def _ensure_settings():
	settings = frappe.get_single("Placement Settings")
	changed = False
	defaults = {
		"annual_service_rate_pct": 12,
		"default_profit_margin_pct": 0,
		"default_interest_rate_pct": 0,
		"outright_floor_pct": 5,
		"rounding_precision": 2,
	}
	for fieldname, value in defaults.items():
		if settings.get(fieldname) is None or settings.get(fieldname) == "":
			settings.set(fieldname, value)
			changed = True
	if changed:
		settings.save(ignore_permissions=True)
