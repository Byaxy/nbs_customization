# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Analyzer Profile resolution for the pricing worksheet."""

import math

import frappe
from frappe.utils import flt

from nbs_customization.utils.pricing import get_current_selling_price

CACHE_PREFIX = "analyzer_profile:"


def clear_analyzer_menu_cache(doc=None, method=None):
	frappe.cache.delete_keys(CACHE_PREFIX)


def get_analyzer_profile(analyzer_item):
	"""Return the Analyzer Profile for *analyzer_item*, or None."""
	if not analyzer_item:
		return None
	name = frappe.db.get_value("Analyzer Profile", {"analyzer_item": analyzer_item}, "name")
	if not name:
		return None
	cache_key = f"{CACHE_PREFIX}{name}"
	cached = frappe.cache.get_value(cache_key)
	if cached:
		return frappe.get_doc(cached)
	doc = frappe.get_doc("Analyzer Profile", name)
	frappe.cache.set_value(cache_key, doc.as_dict(), expires_in_sec=300)
	return doc


def get_profile_test_parameters(analyzer_item):
	profile = get_analyzer_profile(analyzer_item)
	return sorted({row.test_parameter for row in profile.reagents if row.test_parameter}) if profile else []


def resolve_test(analyzer_item, parameter, application=None, sample_type=None, method=None):
	"""Resolve one test from the analyzer profile to its reagent components."""
	if not analyzer_item or not parameter:
		return {}
	profile = get_analyzer_profile(analyzer_item)
	if not profile:
		return {}
	rows = [row for row in profile.reagents if row.test_parameter == parameter]
	if not rows:
		return {}
	return {
		"test_parameter": parameter,
		"application": rows[0].application_code,
		"sample_type": rows[0].sample_type,
		"method": rows[0].method,
		"reagents": [
			{"reagent_item": row.reagent_item, "component_role": row.component_role} for row in rows
		],
	}


def resolve_panel(analyzer_item, panel):
	"""Resolve a Test Panel to profile tests, keeping panel order."""
	rows = frappe.get_all(
		"Test Panel Parameter",
		filters={"parent": panel, "parenttype": "Test Panel"},
		fields=["test_parameter", "sequence", "is_optional"],
		order_by="sequence asc, idx asc",
	)
	result = []
	for row in rows:
		test = resolve_test(analyzer_item, row["test_parameter"])
		if test:
			result.append(
				{
					"test_panel": panel,
					"test_parameter": row["test_parameter"],
					"sequence": row["sequence"],
					"is_optional": row["is_optional"],
					"application": test,
				}
			)
	return result


def resolve_consumable_requirements(analyzer_item):
	profile = get_analyzer_profile(analyzer_item)
	return [row.as_dict() for row in profile.consumables] if profile else []


def resolve_cost_basis(
	analyzer_item,
	term_months,
	operational_days_per_month=0,
	on_date=None,
	monthly_test_volume=0,
):
	"""Calibrators, controls, solutions and maintenance parts over the term."""
	profile = get_analyzer_profile(analyzer_item)
	term_months = flt(term_months)
	if not profile or term_months <= 0:
		return []
	rows = []
	for item in profile.consumables:
		quantity = _consumable_quantity(item, term_months, operational_days_per_month, monthly_test_volume)
		if quantity > 0:
			rows.append(
				_cost_row(
					item.item,
					"Calibration Material"
					if item.role in ("Calibrator", "Control")
					else "Analyzer Consumable",
					f"{profile.name}:{item.role}",
					quantity,
					on_date,
				)
			)
	for part in profile.maintenance:
		quantity = _maintenance_quantity(part, term_months)
		if quantity > 0:
			rows.append(_cost_row(part.item, "Maintenance Part", profile.name, quantity, on_date))
	return rows


def _consumable_quantity(row, term_months, operational_days_per_month, monthly_test_volume=0):
	role = row.role
	if role == "Control":
		daily = flt(row.controls_per_day) or flt(row.qty)
		return daily * flt(operational_days_per_month) * term_months
	if role == "Calibrator":
		frequency = flt(row.calibration_frequency_days) or 30
		events = math.ceil(term_months * 30.44 / frequency)
		per_event = (
			flt(row.qty_per_event) or (flt(row.levels) or 1) * (flt(row.vials_per_calibration) or 1) or 1
		)
		return events * per_event
	basis = row.consumption_basis
	qty = flt(row.qty)
	if basis == "Per Month":
		return qty * term_months
	if basis == "Per Year":
		return qty * term_months / 12
	if basis == "Per Service Interval":
		return qty * flt(row.services_per_year) * term_months / 12
	if basis == "Per Day":
		return qty * flt(operational_days_per_month) * term_months
	if basis == "Per Test":
		return qty * flt(monthly_test_volume) * term_months
	return 0


def _maintenance_quantity(row, term_months):
	if row.action == "Inspect":
		return 0
	term_months = flt(term_months)
	month_no = int(row.month_no or 0)
	if month_no:
		replacements = 0
		month = month_no
		while month <= term_months:
			replacements += 1
			month += 12
	else:
		replacements = math.ceil(term_months / 12)
		if row.action != "As Needed":
			replacements = max(replacements, 1)
	return flt(row.qty) * replacements


def _cost_row(item_code, source_type, source_reference, quantity, on_date=None):
	item = (
		frappe.db.get_value(
			"Item",
			item_code,
			["item_name", "description", "valuation_rate", "last_purchase_rate"],
			as_dict=True,
		)
		or {}
	)
	cogs = frappe.db.get_value("Reagent Specification", {"item": item_code}, "default_cogs_per_unit")
	if not cogs:
		cogs = flt(item.get("valuation_rate")) or flt(item.get("last_purchase_rate")) or 0
	return {
		"item_code": item_code,
		"source_type": source_type,
		"source_reference": source_reference,
		"description": (item.get("description") or item.get("item_name") or "")[:140],
		"quantity_over_term": flt(quantity, 4),
		"cogs_per_unit": flt(cogs),
		"standard_selling_price_per_unit": get_current_selling_price(item_code, on_date),
		"is_auto": 1,
	}
