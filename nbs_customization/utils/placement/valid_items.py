# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Analyzer membership checks for worksheet reagent and consumable lookups."""

import frappe

from nbs_customization.utils.placement.analyzer_menu import (
	get_analyzer_profile,
	resolve_consumable_requirements,
	resolve_test,
)


def get_reagent_items_for_analyzer(analyzer_item):
	"""Items valid for *analyzer_item*: test reagents, consumables and parts."""
	profile = get_analyzer_profile(analyzer_item)
	if not profile:
		return []
	reagents = {row.reagent_item for row in profile.reagents}
	consumables = {row["item"] for row in resolve_consumable_requirements(analyzer_item)}
	maintenance = {row.item for row in profile.maintenance}
	return _item_rows(sorted(reagents | consumables | maintenance))


def require_analyzer_item_read(analyzer_item):
	if analyzer_item and not frappe.has_permission("Item", "read", analyzer_item):
		frappe.throw(
			frappe._("Not permitted to read Item {0}.").format(analyzer_item), frappe.PermissionError
		)


def _item_rows(codes):
	if not codes:
		return []
	items = frappe.db.get_all(
		"Item",
		filters={"name": ("in", codes)},
		fields=["name as item_code", "item_name", "description"],
	)
	roles = dict(
		frappe.db.get_all(
			"Reagent Specification",
			filters={"item": ("in", codes)},
			fields=["item", "reagent_role"],
			as_list=True,
		)
	)
	for row in items:
		row["reagent_role"] = roles.get(row["item_code"])
	return items


def _build_reagent_labels(item_codes):
	if not item_codes:
		return {}
	codes = list(item_codes)
	items = {
		row["name"]: row
		for row in frappe.db.get_all(
			"Item",
			filters={"name": ("in", codes)},
			fields=["name", "item_name", "description"],
		)
	}
	roles = dict(
		frappe.db.get_all(
			"Reagent Specification",
			filters={"item": ("in", codes)},
			fields=["item", "item_role"],
			as_list=True,
		)
	)
	labels = {}
	for code in codes:
		item = items.get(code, {})
		name = (item.get("item_name") or "").strip()
		desc = " ".join((item.get("description") or "").split())[:60]
		role = roles.get(code) or "Unspecified"
		parts = [part for part in (name, desc) if part]
		label = " — ".join(parts) if parts else code
		labels[code] = f"{label} | {role}"
	return labels


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_contract_placement_items(doctype, txt, searchfield, start, page_len, filters):
	"""Search only contract reagent/consumable item lines for a placement contract."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	contract_name = filters.get("contract")
	if not contract_name:
		return []
	frappe.has_permission("Instrument Placement Contract", "read", contract_name, throw=True)

	contract = frappe.get_doc("Instrument Placement Contract", contract_name)
	transaction_type = filters.get("transaction_type")
	reagent_types = {"Contract Reagent Sale", "Contract Free Issue"}
	consumable_types = {"Contract Consumable Replenishment", "Contract Consumable Free Issue"}

	codes = set()
	if transaction_type in reagent_types:
		codes.update(line.item_code for line in contract.contract_reagent_lines if line.item_code)
	elif transaction_type in consumable_types:
		codes.update(line.item_code for line in contract.contract_consumable_lines if line.item_code)
	else:
		codes.update(line.item_code for line in contract.contract_reagent_lines if line.item_code)
		codes.update(line.item_code for line in contract.contract_consumable_lines if line.item_code)

	labels = _build_reagent_labels(codes)
	sorted_codes = sorted(codes)
	if txt:
		needle = txt.lower()
		sorted_codes = [
			code for code in sorted_codes if needle in code.lower() or needle in labels.get(code, "").lower()
		]
	return [[code, labels.get(code, code)] for code in sorted_codes[start : start + page_len]]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_valid_reagent_items(doctype, txt, searchfield, start, page_len, filters):
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	analyzer_item = filters.get("analyzer_item")
	test_parameter = filters.get("test_parameter")
	if not analyzer_item:
		return []
	require_analyzer_item_read(analyzer_item)

	if test_parameter:
		test = resolve_test(analyzer_item, test_parameter)
		codes = {component["reagent_item"] for component in test.get("reagents") or []}
	else:
		codes = {row["item_code"] for row in get_reagent_items_for_analyzer(analyzer_item)}

	labels = _build_reagent_labels(codes)
	sorted_codes = sorted(codes)
	if txt:
		needle = txt.lower()
		sorted_codes = [
			code for code in sorted_codes if needle in code.lower() or needle in labels.get(code, "").lower()
		]
	return [[code, labels.get(code, code)] for code in sorted_codes[start : start + page_len]]


@frappe.whitelist()
def is_reagent_valid_for_parameter(reagent_item, test_parameter, analyzer_item=None):
	if not reagent_item or not test_parameter or not analyzer_item:
		return True
	test = resolve_test(analyzer_item, test_parameter)
	return reagent_item in {component["reagent_item"] for component in test.get("reagents") or []}


def validate_items_belong_to_analyzer(analyzer_item, item_codes, throw=True):
	valid_set = {row["item_code"] for row in get_reagent_items_for_analyzer(analyzer_item)}
	for code in item_codes:
		if code and code not in valid_set:
			message = frappe._(
				"Item {0} is not a reagent, consumable or maintenance part for analyzer {1}. "
				"Add it to the Analyzer Profile."
			).format(frappe.bold(code), frappe.bold(analyzer_item))
			if throw:
				frappe.throw(message)
			return False
	return True
