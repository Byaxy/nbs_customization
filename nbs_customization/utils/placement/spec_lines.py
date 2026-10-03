# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Spec-scoped lookups for the Pricing Worksheet.

All helpers read the analyzer's Instrument Specification, so worksheet
lines stay consistent with what the analyzer supports. Parameter drives:
picking a Test Parameter determines its mapped reagent and pack defaults.
"""

import frappe

from nbs_customization.utils.placement.valid_items import _build_reagent_labels


def _get_spec_name(analyzer_item):
	"""Return the Instrument Specification name for *analyzer_item*, or None."""
	if not analyzer_item:
		return None
	return frappe.db.get_value("Instrument Specification", {"item": analyzer_item}, "name")


def _spec_test_methods(analyzer_item):
	"""Return supported-test-method rows for the analyzer's spec."""
	spec = _get_spec_name(analyzer_item)
	if not spec:
		return []
	return frappe.db.get_all(
		"Instrument Test Method",
		filters={"parent": spec},
		fields=[
			"test_parameter",
			"required_reagent",
			"default_pack_volume_ml",
			"default_tests_per_pack",
			"default_cogs_per_pack",
		],
	)


def _resolve_pack_defaults(row):
	"""Fill empty spec-row pack fields from the reagent's Reagent Specification."""
	fields = ["default_pack_volume_ml", "default_tests_per_pack", "default_cogs_per_pack"]
	missing = [f for f in fields if not row.get(f) and row.get("required_reagent")]
	if not missing:
		return row
	rs = frappe.db.get_value(
		"Reagent Specification",
		{"item": row["required_reagent"]},
		["default_pack_volume_ml", "default_tests_per_pack", "default_cogs_per_pack"],
		as_dict=True,
	)
	if rs:
		for f in missing:
			row[f] = rs.get(f) or 0
	return row


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_spec_test_parameters(doctype, txt, searchfield, start, page_len, filters):
	"""Test Parameters on the analyzer's spec, as ``[code, parameter_name]``."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	rows = _spec_test_methods(filters.get("analyzer_item"))
	if not rows:
		return []
	names = {
		r["name"]: r.get("parameter_name", "")
		for r in frappe.db.get_all(
			"Test Parameter",
			filters={"name": ("in", [m["test_parameter"] for m in rows if m["test_parameter"]])},
			fields=["name", "parameter_name"],
		)
	}
	if txt:
		txt_lower = txt.lower()
		rows = [
			m
			for m in rows
			if txt_lower in (m["test_parameter"] or "").lower()
			or txt_lower in names.get(m["test_parameter"], "").lower()
		]
	rows = sorted(rows, key=lambda m: m["test_parameter"] or "")
	page = rows[start : start + page_len]
	return [[m["test_parameter"], names.get(m["test_parameter"], "")] for m in page]


@frappe.whitelist()
def get_spec_test_method_details(analyzer_item: str, test_parameter: str):
	"""Mapped reagent, description + pack defaults for *test_parameter* on the spec."""
	if not analyzer_item or not test_parameter:
		return {}
	for row in _spec_test_methods(analyzer_item):
		if row["test_parameter"] == test_parameter:
			details = _resolve_pack_defaults(dict(row))
			details["description"] = (
				frappe.db.get_value("Item", details["required_reagent"], "description") or ""
			)
			return details
	return {}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_spec_consumables(doctype, txt, searchfield, start, page_len, filters):
	"""Consumable items on the analyzer's spec, with rich dropdown labels."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	spec = _get_spec_name(filters.get("analyzer_item"))
	if not spec:
		return []
	rows = frappe.db.get_all(
		"Instrument Consumable Requirement",
		filters={"parent": spec},
		pluck="consumable_item",
		distinct=True,
	)
	labels = _build_reagent_labels(rows)
	codes = sorted(rows)
	if txt:
		txt_lower = txt.lower()
		codes = [c for c in codes if txt_lower in c.lower() or txt_lower in labels.get(c, "").lower()]
	return [[c, labels.get(c, c)] for c in codes[start : start + page_len]]


@frappe.whitelist()
def get_analyzer_landed_cost(analyzer_item: str):
	"""Latest valuation/purchase rate for *analyzer_item*; first positive source wins."""
	if not analyzer_item:
		return {"rate": 0}
	incoming = frappe.db.get_all(
		"Stock Ledger Entry",
		filters={"item_code": analyzer_item, "actual_qty": [">", 0], "is_cancelled": 0},
		fields=["valuation_rate"],
		order_by="posting_date desc, posting_time desc, creation desc",
		limit=1,
	)
	for source in (
		(incoming[0].get("valuation_rate") if incoming else 0),
		frappe.db.get_value("Item", analyzer_item, "valuation_rate"),
		frappe.db.get_value("Item", analyzer_item, "last_purchase_rate"),
		frappe.db.get_value(
			"Item Price",
			{"item_code": analyzer_item, "price_list": "Standard Buying"},
			"price_list_rate",
		),
	):
		if source and source > 0:
			return {"rate": source}
	return {"rate": 0}


@frappe.whitelist()
def get_spec_consumable_details(analyzer_item: str, consumable_item: str):
	"""Qty/frequency/cost for *consumable_item* from the analyzer's spec row."""
	if not analyzer_item or not consumable_item:
		return {}
	spec = _get_spec_name(analyzer_item)
	row = None
	if spec:
		row = frappe.db.get_value(
			"Instrument Consumable Requirement",
			{"parent": spec, "consumable_item": consumable_item},
			["consumption_qty", "consumption_frequency", "services_per_year", "default_cogs_per_unit"],
			as_dict=True,
		)
	row = dict(row) if row else {}
	if not row.get("consumption_qty") or not row.get("default_cogs_per_unit"):
		rs = frappe.db.get_value(
			"Reagent Specification",
			{"item": consumable_item},
			["default_consumption_qty", "default_consumption_frequency", "default_cogs_per_unit"],
			as_dict=True,
		)
		if rs:
			if not row.get("consumption_qty"):
				row["consumption_qty"] = rs.get("default_consumption_qty") or 0
			if not row.get("consumption_frequency"):
				row["consumption_frequency"] = rs.get("default_consumption_frequency")
			if not row.get("default_cogs_per_unit"):
				row["default_cogs_per_unit"] = rs.get("default_cogs_per_unit") or 0
	return row
