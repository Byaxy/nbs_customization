# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Contract-free analyzer menu resolver."""

import math

import frappe
from frappe.utils import flt, getdate, today

from nbs_customization.utils.pricing import get_current_selling_price

CACHE_PREFIX = "analyzer_menu:"
CACHE_TTL = 300


def clear_analyzer_menu_cache(doc=None, method=None):
	"""Clear cached analyzer menus after a master change."""
	frappe.cache.delete_keys(CACHE_PREFIX)


def _cache_key(analyzer_item):
	return f"{CACHE_PREFIX}{analyzer_item}"


def _is_valid(row, on_date=None):
	on_date = getdate(on_date or today())
	valid_from = row.get("valid_from")
	valid_upto = row.get("valid_upto")
	if valid_from and getdate(valid_from) > on_date:
		return False
	if valid_upto and getdate(valid_upto) < on_date:
		return False
	return True


def _get_applications(analyzer_item):
	return frappe.get_all(
		"Analyzer Test Application",
		filters={"analyzer_item": analyzer_item},
		fields=[
			"name",
			"analyzer_item",
			"test_parameter",
			"assay_group",
			"application_code",
			"analyzer_test_code",
			"sample_type",
			"method",
			"result_type",
			"is_default",
			"valid_from",
			"valid_upto",
		],
		order_by="application_code asc, name asc",
	)


def _get_assay_groups(analyzer_item):
	groups = frappe.get_all(
		"Analyzer Assay Group",
		filters={"analyzer_item": analyzer_item},
		fields=["name", "group_code", "group_name", "test_panel", "run_basis", "sample_type"],
		order_by="group_code asc, name asc",
	)
	for group in groups:
		group["tests"] = frappe.get_all(
			"Assay Group Test",
			filters={"parent": group["name"], "parenttype": "Analyzer Assay Group"},
			fields=["test_parameter", "sequence", "is_optional"],
			order_by="sequence asc, idx asc",
		)
		group["reagents"] = frappe.get_all(
			"Assay Group Reagent",
			filters={"parent": group["name"], "parenttype": "Analyzer Assay Group"},
			fields=[
				"reagent_item",
				"component_role",
				"consumption_basis",
				"qty_per_group_test",
				"qty_per_run",
				"qty_per_day",
				"efficiency_pct",
				"allocation_method",
				"allocation_weight",
				"tests_per_pack_override",
				"pack_volume_ml_override",
			],
			order_by="idx asc",
		)
	return groups


def _get_panels(applications):
	parameters = {row["test_parameter"] for row in applications if row.get("test_parameter")}
	if not parameters:
		return []
	panel_names = frappe.get_all(
		"Test Panel Parameter",
		filters={"test_parameter": ("in", list(parameters))},
		pluck="parent",
		distinct=True,
	)
	if not panel_names:
		return []
	return frappe.get_all(
		"Test Panel",
		filters={"name": ("in", panel_names), "is_active": 1},
		fields=["name", "panel_code", "panel_name", "panel_type", "specialty"],
		order_by="panel_code asc",
	)


def _build_menu(analyzer_item):
	applications = [row for row in _get_applications(analyzer_item) if _is_valid(row)]
	app_names = {row["name"] for row in applications}
	for row in applications:
		row["reagents"] = frappe.get_all(
			"Analyzer Application Reagent",
			filters={"parent": row["name"], "parenttype": "Analyzer Test Application"},
			fields=[
				"reagent_item",
				"component_role",
				"consumption_basis",
				"qty_per_test",
				"qty_per_day",
				"qty_per_run",
				"qty_per_calibration",
				"efficiency_pct",
				"calibration_control_pct_override",
				"dead_volume_pct_override",
				"tests_per_pack_override",
				"pack_volume_ml_override",
				"allocation_weight",
			],
			order_by="idx asc",
		)
	return {
		"applications": applications,
		"assay_groups": _get_assay_groups(analyzer_item),
		"panels": _get_panels(applications),
		"application_names": sorted(app_names),
	}


def get_analyzer_menu(analyzer_item):
	"""Return the cached menu for *analyzer_item*."""
	if not analyzer_item:
		return {"applications": [], "assay_groups": [], "panels": [], "application_names": []}
	key = _cache_key(analyzer_item)
	cached = frappe.cache.get_value(key)
	if cached:
		return cached
	menu = _build_menu(analyzer_item)
	frappe.cache.set_value(key, menu, expires_in_sec=CACHE_TTL)
	return menu


def resolve_menu(analyzer_item):
	"""Return panels, applications, and assay groups for an analyzer."""
	return get_analyzer_menu(analyzer_item)


def resolve_default_application(analyzer_item, parameter, sample_type=None, method=None):
	"""Return the default application name for the key, or None."""
	menu = get_analyzer_menu(analyzer_item)
	candidates = [
		row for row in menu["applications"] if row["test_parameter"] == parameter and row.get("is_default")
	]
	if not candidates:
		return None

	def score(row):
		return (
			1 if sample_type and row.get("sample_type") == sample_type else 0,
			1 if method and row.get("method") == method else 0,
			1 if not sample_type and not row.get("sample_type") else 0,
		)

	candidates.sort(key=score, reverse=True)
	return candidates[0]["name"]


def resolve_test(analyzer_item, parameter, application=None, sample_type=None, method=None):
	"""Resolve one test to its application and reagent components."""
	menu = get_analyzer_menu(analyzer_item)
	app_name = application or resolve_default_application(analyzer_item, parameter, sample_type, method)
	if not app_name:
		return {}
	for row in menu["applications"]:
		if row["name"] == app_name:
			return dict(row)
	return {}


def resolve_panel(analyzer_item, panel, group_volumes=None):
	"""Resolve a panel to test rows. Group volumes are passed through for Plan 2."""
	group_volumes = group_volumes or {}
	parameters = frappe.get_all(
		"Test Panel Parameter",
		filters={"parent": panel, "parenttype": "Test Panel"},
		fields=["test_parameter", "sequence", "is_optional"],
		order_by="sequence asc, idx asc",
	)
	rows = []
	for param in parameters:
		test = resolve_test(analyzer_item, param["test_parameter"])
		if not test:
			continue
		rows.append(
			{
				"test_panel": panel,
				"test_parameter": param["test_parameter"],
				"sequence": param["sequence"],
				"is_optional": param["is_optional"],
				"application": test,
				"group_sample_volume": group_volumes.get(test.get("assay_group")),
			}
		)
	return rows


def _scope_includes(requirement, app_names, group_names):
	scope = requirement.get("scope")
	if scope == "All Assays":
		return True
	if scope == "Assay Group":
		return requirement.get("assay_group") in group_names
	if scope == "Selected Applications":
		selected = frappe.get_all(
			"Analyzer Consumable Application",
			filters={"parent": requirement["name"], "parenttype": "Analyzer Consumable Requirement"},
			pluck="application",
		)
		return bool(set(selected) & app_names)
	return False


def resolve_consumable_requirements(analyzer_item, applications=None, assay_groups=None):
	"""Expand and aggregate consumable requirements by item."""
	menu = get_analyzer_menu(analyzer_item)
	app_names = set(applications or menu["application_names"])
	group_names = set(assay_groups or [g["name"] for g in menu["assay_groups"]])
	requirements = frappe.get_all(
		"Analyzer Consumable Requirement",
		filters={"analyzer_item": analyzer_item},
		fields=[
			"name",
			"consumable_item",
			"consumable_role",
			"scope",
			"assay_group",
			"consumption_basis",
			"qty",
			"services_per_year",
		],
	)
	aggregated = {}
	for row in requirements:
		if not _scope_includes(row, app_names, group_names):
			continue
		key = (row["consumable_item"], row["consumable_role"], row["consumption_basis"])
		if key not in aggregated:
			aggregated[key] = dict(row, qty=0)
		aggregated[key]["qty"] += row["qty"] or 0
	return list(aggregated.values())


def resolve_calibration_requirements(analyzer_item, applications=None):
	"""Expand calibration rules and return unique material requirements."""
	menu = get_analyzer_menu(analyzer_item)
	app_names = set(applications or menu["application_names"])
	rules = frappe.get_all(
		"Analyzer Calibration Rule",
		filters={"analyzer_item": analyzer_item},
		fields=["name", "rule_name", "scope"],
	)
	result = {}
	for rule in rules:
		if rule["scope"] == "Selected Applications":
			selected = frappe.get_all(
				"Analyzer Calibration Application",
				filters={"parent": rule["name"], "parenttype": "Analyzer Calibration Rule"},
				pluck="application",
			)
			if not set(selected) & app_names:
				continue
		materials = frappe.get_all(
			"Analyzer Calibration Material",
			filters={"parent": rule["name"], "parenttype": "Analyzer Calibration Rule"},
			fields=[
				"material_item",
				"material_role",
				"levels",
				"vials_per_calibration",
				"tests_per_vial",
				"calibration_frequency_days",
				"onboard_stability_days",
				"controls_per_day",
				"qty_per_event",
			],
		)
		for material in materials:
			key = (
				material["material_item"],
				material["material_role"],
				material["calibration_frequency_days"],
				material["onboard_stability_days"],
				material["controls_per_day"],
			)
			current = result.get(key)
			if not current or (material["qty_per_event"] or 0) > (current["qty_per_event"] or 0):
				result[key] = dict(material, rule=rule["name"])
	return list(result.values())


def resolve_maintenance(part, term_months):
	"""Return quantity over term for one Analyzer Maintenance Part."""
	if not part:
		return 0
	term_years = (term_months or 0) / 12
	part_name = part if isinstance(part, str) else part.name
	schedule = frappe.get_all(
		"Analyzer Maintenance Schedule",
		filters={"parent": part_name, "parenttype": "Analyzer Maintenance Part"},
		fields=["month_no", "action"],
	)
	replace_months = len([row for row in schedule if row["action"] == "Replace"])
	as_needed = 1 if any(row["action"] == "As Needed" for row in schedule) else 0
	qty = flt(frappe.db.get_value("Analyzer Maintenance Part", part_name, "qty"))
	replacements = math.ceil(replace_months * term_years) if replace_months else 0
	as_needed_qty = math.ceil(term_years) if as_needed else 0
	return qty * (replacements + as_needed_qty)


def resolve_price(item, price_list=None, uom=None):
	"""Return the current Standard Selling rate for an item."""
	return get_current_selling_price(item)


def apply_pack_time_floor(packs, onboard_stability_days=None, shelf_life_days=None):
	"""No-op extension point for a future pack-count time floor."""
	return packs
