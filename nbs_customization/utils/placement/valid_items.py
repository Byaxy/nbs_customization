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


def _get_panel_for_parameter(test_parameter):
	"""Return the Test Panel Group for a Test Parameter, or None."""
	if not test_parameter:
		return None
	return frappe.db.get_value("Test Parameter", test_parameter, "test_panel_group")


def require_analyzer_item_read(analyzer_item):
	"""Throw PermissionError unless the caller may read the analyzer Item."""
	if analyzer_item and not frappe.has_permission("Item", "read", analyzer_item):
		frappe.throw(
			frappe._("Not permitted to read Item {0}.").format(analyzer_item), frappe.PermissionError
		)


def _restrict_items_to_panel(item_codes, panel):
	"""Keep items whose Reagent Spec panel matches *panel*, plus universals."""
	if not panel or not item_codes:
		return set(item_codes)
	rs_rows = frappe.db.get_all(
		"Reagent Specification",
		filters={"item": ("in", list(item_codes))},
		fields=["item", "test_panel_group"],
	)
	panel_by_item = {r["item"]: r.get("test_panel_group") for r in rs_rows}
	kept = {
		code
		for code in item_codes
		# No Reagent Specification row: panel unknown, keep (spec permits with warning).
		if code not in panel_by_item or not panel_by_item[code] or panel_by_item[code] == panel
	}
	return kept


def _build_reagent_labels(item_codes):
	"""Map item code -> rich dropdown label with name, description, panel."""
	if not item_codes:
		return {}
	codes = list(item_codes)
	items = {
		r["name"]: r
		for r in frappe.db.get_all(
			"Item",
			filters={"name": ("in", codes)},
			fields=["name", "item_name", "description"],
		)
	}
	rs_map = dict(
		frappe.db.get_all(
			"Reagent Specification",
			filters={"item": ("in", codes)},
			fields=["item", "test_panel_group"],
			as_list=True,
		)
	)
	labels = {}
	for code in codes:
		item = items.get(code, {})
		name = (item.get("item_name") or "").strip()
		desc = " ".join((item.get("description") or "").split())[:60]
		panel = rs_map.get(code)
		panel_txt = panel or "Universal"
		if name and desc:
			labels[code] = f"{name} — {desc} | Panel: {panel_txt}"
		elif name:
			labels[code] = f"{name} | Panel: {panel_txt}"
		elif desc:
			labels[code] = f"{desc} | Panel: {panel_txt}"
		else:
			labels[code] = f"Panel: {panel_txt}"
	return labels


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

	panels_to_check = {r["test_panel_group"] for r in all_rs if r["test_panel_group"]}
	if panels_to_check:
		panel_info = frappe.db.get_all(
			"Test Panel Group",
			filters={"name": ("in", list(panels_to_check))},
			fields=["name", "analyzer_type"],
		)
		matching_panels = {
			p["name"] for p in panel_info if not p.get("analyzer_type") or p["analyzer_type"] == analyzer_type
		}
	else:
		matching_panels = set()

	return {
		r["item"] for r in all_rs if not r["test_panel_group"] or r["test_panel_group"] in matching_panels
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_valid_reagent_items(doctype, txt, searchfield, start, page_len, filters):
	"""
	Frappe search-query function for Link fields pointing to reagent/consumable items.

	Accepts filter modes via the *filters* dict (passed from JS):
	- ``analyzer_item`` — return only items valid for that analyzer's Instrument Specification
	- ``reagent_role`` — return only items whose Reagent Specification matches the given role
	- ``analyzer_type`` — further restrict to items whose Test Panel Group matches this type
	                     or is universal (no panel / no type).
	- ``test_parameter`` — keep only reagents usable for that test (same panel, plus
	                       universal reagents with no panel).

	Returns ``[item_code, label]`` tuples where label carries item name,
	description, and panel for a richer dropdown.
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	analyzer_item = filters.get("analyzer_item")
	reagent_role = filters.get("reagent_role")
	analyzer_type = filters.get("analyzer_type")
	test_parameter = filters.get("test_parameter")

	if analyzer_item:
		require_analyzer_item_read(analyzer_item)
		items = get_reagent_items_for_analyzer(analyzer_item)
		codes = {i["item_code"] for i in items}
		if analyzer_type and codes:
			restrict = _get_items_for_role(reagent_role or None, analyzer_type)
			codes = {c for c in codes if c in restrict}
	elif reagent_role or analyzer_type:
		codes = _get_items_for_role(reagent_role or None, analyzer_type)
	else:
		codes = set()
		if txt:
			for field in ("name", "item_name"):
				try:
					rows = frappe.db.get_all(
						"Item", filters={field: ("like", f"%{txt}%")}, pluck="name", limit=50
					)
					codes.update(rows)
				except Exception:
					continue
		if codes:
			rs = frappe.db.get_all("Reagent Specification", pluck="item", limit=1000)
			codes = codes.intersection(set(rs))

	if not codes:
		return []

	if test_parameter:
		panel = _get_panel_for_parameter(test_parameter)
		codes = _restrict_items_to_panel(codes, panel)

	labels = _build_reagent_labels(codes)

	codes = sorted(codes)
	if txt:
		txt_lower = txt.lower()
		codes = [c for c in codes if txt_lower in c.lower() or txt_lower in labels.get(c, "").lower()]

	return [[c, labels.get(c, c)] for c in codes[start : start + page_len]]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_test_parameters_for_analyzer_type(doctype, txt, searchfield, start, page_len, filters):
	"""
	Frappe search-query function for Test Parameter Link fields.
	Restricts to parameters whose Test Panel Group matches the given analyzer_type,
	plus universal parameters with no panel. Matches typed text against both
	parameter code (name) and parameter name. Returns ``[name, parameter_name]``
	so the dropdown shows code plus name.
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
	analyzer_type = filters.get("analyzer_type")

	or_filters = None
	if txt:
		like = f"%{txt}%"
		or_filters = [
			["Test Parameter", "name", "like", like],
			["Test Parameter", "parameter_name", "like", like],
		]

	def _fetch(tp_filters):
		return frappe.db.get_all(
			"Test Parameter",
			filters=tp_filters,
			or_filters=or_filters,
			fields=["name", "parameter_name", "test_panel_group"],
			order_by="name asc",
		)

	if analyzer_type:
		all_panels = frappe.db.get_all("Test Panel Group", fields=["name", "analyzer_type"])
		matching = {
			p["name"] for p in all_panels if not p.get("analyzer_type") or p["analyzer_type"] == analyzer_type
		}
		# Panel filter runs in the DB (two queries OR-ed in Python) so valid
		# parameters are never truncated by an unfiltered row limit.
		rows = _fetch({"test_panel_group": ("is", "not set")})
		if matching:
			rows += _fetch({"test_panel_group": ("in", list(matching))})
	else:
		rows = _fetch(None)

	rows = sorted(rows, key=lambda r: r["name"])
	page = rows[start : start + page_len]
	return [[r["name"], r["parameter_name"]] for r in page]


@frappe.whitelist()
def is_reagent_valid_for_parameter(reagent_item, test_parameter):
	"""True when *reagent_item* may be used for *test_parameter* (same panel or universal)."""
	if not reagent_item or not test_parameter:
		return True
	panel = _get_panel_for_parameter(test_parameter)
	if not panel:
		return True
	kept = _restrict_items_to_panel({reagent_item}, panel)
	return reagent_item in kept


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
