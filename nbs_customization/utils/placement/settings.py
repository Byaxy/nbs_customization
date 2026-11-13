# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Placement policy defaults.

The Single doctype may not exist yet on a fresh site during migration, so the
fallbacks mirror the doctype defaults.
"""

import frappe

DEFAULTS = {
	"annual_service_rate_pct": 12.0,
	"default_profit_margin_pct": 0.0,
	"default_interest_rate_pct": 0.0,
	"outright_floor_pct": 5.0,
	"rounding_precision": 2,
}


def get_placement_settings():
	"""Return a dict of placement defaults, falling back to code defaults."""
	try:
		doc = frappe.get_cached_doc("Placement Settings")
	except Exception:
		return dict(DEFAULTS)
	values = {}
	for fieldname, default in DEFAULTS.items():
		value = doc.get(fieldname)
		values[fieldname] = default if value is None or value == "" else value
	return values
