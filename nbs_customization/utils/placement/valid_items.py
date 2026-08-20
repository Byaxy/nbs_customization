# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe


def get_reagent_items_for_analyzer(analyzer_item):
	"""
	Return a list of Item codes that are valid reagents/consumables
	for the given analyzer, per its Instrument Specification.

	Returns a list of dicts with keys: item_code, item_name, description, reagent_role.
	Used internally by ``validate_items_belong_to_analyzer`` and tests.
	"""
	spec = frappe.db.get_value("Instrument Specification", {"item": analyzer_item}, "name")
	if not spec:
		return []

	reagent_items = frappe.db.get_all(
		"Instrument Test Method",
		filters={"parent": spec},
		fields=["required_reagent"],
		pluck="required_reagent",
		distinct=True,
	)

	consumable_items = frappe.db.get_all(
		"Instrument Consumable Requirement",
		filters={"parent": spec},
		fields=["consumable_item"],
		pluck="consumable_item",
		distinct=True,
	)

	all_items = set(list(reagent_items) + list(consumable_items))

	if not all_items:
		return []

	result = frappe.db.get_all(
		"Item",
		filters={"name": ("in", list(all_items))},
		fields=["name as item_code", "item_name", "description"],
	)

	role_map = dict(
		frappe.db.get_all(
			"Reagent Specification",
			filters={"item": ("in", list(all_items))},
			fields=["item", "reagent_role"],
			as_list=True,
		)
	)

	for r in result:
		r["reagent_role"] = role_map.get(r["item_code"])

	return result


def _get_items_for_role(role, analyzer_type=None):
	"""
	Return a set of item codes whose Reagent Specification matches *role*
	and, when *analyzer_type* is given, also matches that type — or is universal.

	An item is "universal" if its Reagent Spec has no ``test_panel_group``,
	or the linked Test Panel Group has no ``analyzer_type``.
	"""
	all_rs = frappe.db.get_all(
		"Reagent Specification",
		filters={"reagent_role": role},
		fields=["item", "test_panel_group"],
	)

	if not analyzer_type:
		return {r["item"] for r in all_rs}

	panels_to_check = {
		r["test_panel_group"] for r in all_rs if r["test_panel_group"]
	}
	if panels_to_check:
		panel_info = frappe.db.get_all(
			"Test Panel Group",
			filters={"name": ("in", list(panels_to_check))},
			fields=["name", "analyzer_type"],
		)
		matching_panels = {
			p["name"] for p in panel_info
			if not p.get("analyzer_type") or p["analyzer_type"] == analyzer_type
		}
	else:
		matching_panels = set()

	return {
		r["item"] for r in all_rs
		if not r["test_panel_group"] or r["test_panel_group"] in matching_panels
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_valid_reagent_items(doctype, txt, searchfield, start, page_len, filters):
	"""
	Frappe search-query function for Link fields pointing to reagent/consumable items.

	Accepts three filter modes via the *filters* dict (passed from JS):
	- ``analyzer_item`` — return only items valid for that analyzer's Instrument Specification
	- ``reagent_role`` — return only items whose Reagent Specification matches the given role
	- ``analyzer_type`` — further restrict to items whose Test Panel Group matches this type
	                     or is universal (no panel / no type).

	Returns a list of ``[item_code, item_name]`` tuples for the search widget.
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	analyzer_item = filters.get("analyzer_item")
	reagent_role = filters.get("reagent_role")
	analyzer_type = filters.get("analyzer_type")

	if analyzer_item:
		items = get_reagent_items_for_analyzer(analyzer_item)
		valid = {i["item_code"]: i["item_name"] for i in items}
		if analyzer_type and valid:
			restrict = _get_items_for_role(reagent_role or None, analyzer_type)
			valid = {k: v for k, v in valid.items() if k in restrict}
	else:
		role = reagent_role or None
		items = _get_items_for_role(role, analyzer_type)
		if not items:
			return []
		valid = dict(
			frappe.db.get_all(
				"Item",
				filters={"name": ("in", list(items))},
				fields=["name", "item_name"],
				as_list=True,
			)
		)

	codes = list(valid.keys())
	if txt:
		txt_lower = txt.lower()
		codes = [
			c for c in codes
			if txt_lower in c.lower() or txt_lower in valid.get(c, "").lower()
		]

	return [[c, valid.get(c, c)] for c in codes[start:start + page_len]]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_test_parameters_for_analyzer_type(doctype, txt, searchfield, start, page_len, filters):
	"""
	Frappe search-query function for Test Parameter Link fields.
	Restricts to parameters whose Test Panel Group matches the given analyzer_type,
	or whose panel has no type (universal). Returns all parameters when
	no analyzer_type filter is provided.
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	analyzer_type = filters.get("analyzer_type")

	tp_filters = {"parameter_name": ("like", f"%{txt}%")}

	if analyzer_type:
		all_panels = frappe.db.get_all(
			"Test Panel Group", fields=["name", "analyzer_type"]
		)
		panel_names = [
			p["name"] for p in all_panels
			if not p.get("analyzer_type") or p["analyzer_type"] == analyzer_type
		]
		if not panel_names:
			return []
		tp_filters["test_panel_group"] = ("in", panel_names)

	return frappe.db.get_all(
		"Test Parameter",
		filters=tp_filters,
		fields=["name", "parameter_name"],
		as_list=True,
		offset=start,
		limit=page_len,
	)


def validate_items_belong_to_analyzer(analyzer_item, item_codes, throw=True):
	"""
	Server-side validation: raise if any item in *item_codes* is not a valid
	reagent/consumable for *analyzer_item*.

	Returns True/False. If *throw* is True, calls ``frappe.throw`` on the
	first invalid item with a clear message.
	"""
	valid = get_reagent_items_for_analyzer(analyzer_item)
	valid_set = {v["item_code"] for v in valid}

	for code in item_codes:
		if code and code not in valid_set:
			msg = frappe._(
				"Item {0} is not a valid reagent or consumable for analyzer {1}. "
				"Please select an item listed in the analyzer's Instrument Specification."
			).format(frappe.bold(code), frappe.bold(analyzer_item))
			if throw:
				frappe.throw(msg)
			return False
	return True
