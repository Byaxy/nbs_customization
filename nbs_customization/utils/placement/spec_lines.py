# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Analyzer-scoped lookups for the Pricing Worksheet."""

import frappe
from frappe.utils import flt

from nbs_customization.utils.placement.analyzer_menu import (
	get_profile_test_parameters,
	resolve_consumable_requirements,
	resolve_cost_basis,
	resolve_panel,
	resolve_test,
)
from nbs_customization.utils.placement.valid_items import _build_reagent_labels, require_analyzer_item_read
from nbs_customization.utils.pricing import get_current_selling_price

FREQUENCY_BY_BASIS = {
	"Per Month": "Per Month",
	"Per Service Interval": "Per Service Interval",
	"Per Year": "Per Year",
}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_analyzer_test_parameters(doctype, txt, searchfield, start, page_len, filters):
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	analyzer_item = filters.get("analyzer_item")
	require_analyzer_item_read(analyzer_item)
	codes = get_profile_test_parameters(analyzer_item)
	if not codes:
		return []
	names = {
		row["name"]: row.get("parameter_name", "")
		for row in frappe.db.get_all(
			"Test Parameter",
			filters={"name": ("in", codes)},
			fields=["name", "parameter_name"],
		)
	}
	if txt:
		needle = txt.lower()
		codes = [
			code for code in codes if needle in code.lower() or needle in (names.get(code) or "").lower()
		]
	return [[code, names.get(code, "")] for code in codes[start : start + page_len]]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_test_parameters(doctype, txt, searchfield, start, page_len, filters):
	"""Search Test Parameters, returning code and parameter name."""
	or_filters = []
	if txt:
		or_filters = [
			["name", "like", f"%{txt}%"],
			["parameter_name", "like", f"%{txt}%"],
		]
	rows = frappe.get_all(
		"Test Parameter",
		or_filters=or_filters,
		fields=["name", "parameter_name"],
		order_by="name asc",
		limit_start=start,
		limit_page_length=page_len,
	)
	return [
		[
			row["name"],
			f"{row['name']} — {row['parameter_name']}" if row.get("parameter_name") else row["name"],
		]
		for row in rows
	]


@frappe.whitelist()
def get_test_reagent_components(analyzer_item: str, test_parameter: str, posting_date: str | None = None):
	if not analyzer_item or not test_parameter:
		return []
	require_analyzer_item_read(analyzer_item)
	test = resolve_test(analyzer_item, test_parameter)
	return [_component_details(component, posting_date) for component in test.get("reagents", [])]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_analyzer_consumables(doctype, txt, searchfield, start, page_len, filters):
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	analyzer_item = filters.get("analyzer_item")
	require_analyzer_item_read(analyzer_item)
	codes = sorted({row["item"] for row in resolve_consumable_requirements(analyzer_item)})
	if not codes:
		return []
	labels = _build_reagent_labels(codes)
	if txt:
		needle = txt.lower()
		codes = [code for code in codes if needle in code.lower() or needle in labels.get(code, "").lower()]
	return [[code, labels.get(code, code)] for code in codes[start : start + page_len]]


@frappe.whitelist()
def get_analyzer_consumable_details(analyzer_item: str, consumable_item: str):
	if not analyzer_item or not consumable_item:
		return {}
	require_analyzer_item_read(analyzer_item)
	rows = [row for row in resolve_consumable_requirements(analyzer_item) if row["item"] == consumable_item]
	if not rows:
		return {}
	row = rows[0]
	details = {
		"consumption_qty": flt(row.get("qty")),
		"consumption_frequency": FREQUENCY_BY_BASIS.get(row.get("consumption_basis")),
		"services_per_year": flt(row.get("services_per_year")),
	}
	details.update(_consumable_defaults(consumable_item))
	return details


@frappe.whitelist()
def expand_panel(analyzer_item: str, panel: str, posting_date: str | None = None):
	if not analyzer_item or not panel:
		return []
	require_analyzer_item_read(analyzer_item)
	rows = []
	for test in resolve_panel(analyzer_item, panel):
		application = test.get("application") or {}
		for component in application.get("reagents") or []:
			details = _component_details(component, posting_date)
			details.update(
				{"test_parameter": test["test_parameter"], "application": application.get("application")}
			)
			rows.append(details)
	return rows


@frappe.whitelist()
def get_analyzer_cost_basis(
	analyzer_item: str, term_months: float = 0, operational_days_per_month: float = 0
):
	if not analyzer_item or not term_months:
		return []
	require_analyzer_item_read(analyzer_item)
	return resolve_cost_basis(analyzer_item, term_months, operational_days_per_month)


@frappe.whitelist()
def get_analyzer_standard_selling_price(analyzer_item: str, posting_date: str | None = None):
	"""Return the Standard Selling rate for *analyzer_item* on *posting_date*."""
	if not analyzer_item:
		return {"rate": 0}
	require_analyzer_item_read(analyzer_item)
	return {"rate": get_current_selling_price(analyzer_item, posting_date)}


@frappe.whitelist()
def get_analyzer_landed_cost(analyzer_item: str):
	if not analyzer_item:
		return {"rate": 0}
	require_analyzer_item_read(analyzer_item)
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
			"Item Price", {"item_code": analyzer_item, "price_list": "Standard Buying"}, "price_list_rate"
		),
	):
		if source and source > 0:
			return {"rate": source}
	return {"rate": 0}


def _component_details(component, on_date=None):
	item_code = component.get("reagent_item")
	details = {
		"reagent_item": item_code,
		"component_role": component.get("component_role"),
		"description": frappe.db.get_value("Item", item_code, "description") or "",
		"standard_selling_price_per_pack": get_current_selling_price(item_code, on_date),
	}
	details.update(_reagent_defaults(item_code))
	return details


def _reagent_defaults(item_code):
	fields = ["default_pack_volume_ml", "default_tests_per_pack", "default_cogs_per_pack"]
	row = frappe.db.get_value("Reagent Specification", {"item": item_code}, fields, as_dict=True)
	return {field: flt(row.get(field)) for field in fields} if row else {field: 0 for field in fields}


def _consumable_defaults(item_code):
	row = frappe.db.get_value(
		"Reagent Specification",
		{"item": item_code},
		["default_consumption_qty", "default_consumption_frequency", "default_cogs_per_unit"],
		as_dict=True,
	)
	if not row:
		return {}
	return {
		"default_consumption_qty": flt(row.get("default_consumption_qty")),
		"default_consumption_frequency": row.get("default_consumption_frequency"),
		"default_cogs_per_unit": flt(row.get("default_cogs_per_unit")),
	}
