import frappe
from frappe import _


REPORT_CONFIG = {
	"Stock Balance": {
		"remove_columns": ["item_name"],
	},
	"Stock Ledger": {
		"remove_columns": ["item_name"],
	},
}

DESCRIPTION_COLUMN = {
	"label": _("Description"),
	"fieldname": "description",
	"fieldtype": "Small Text",
	"width": 220,
}


@frappe.whitelist()
def run(
	report_name: str,
	filters=None,
	user: str | None = None,
	ignore_prepared_report: bool = False,
	custom_columns=None,
	is_tree: bool = False,
	parent_field: str | None = None,
	are_default_filters: bool = True,
	js_filters=None,
):
	"""Wrapper around frappe.desk.query_report.run.

	Registered via hooks.py -> override_whitelisted_methods.
	"""
	from frappe.desk.query_report import run as _original_run

	result = _original_run(
		report_name=report_name,
		filters=filters,
		user=user,
		ignore_prepared_report=ignore_prepared_report,
		custom_columns=custom_columns,
		is_tree=is_tree,
		parent_field=parent_field,
		are_default_filters=are_default_filters,
		js_filters=js_filters,
	)

	config = REPORT_CONFIG.get(report_name)
	if not config:
		return result

	try:
		return _apply_column_customizations(report_name, result, config)
	except Exception:
		frappe.log_error(
			title=f"NBS report_customizer error for '{report_name}'",
			message=frappe.get_traceback(),
		)
		return result

def _apply_column_customizations(report_name: str, result: dict, config: dict) -> dict:
	columns = result.get("columns") or []
	data = result.get("result") or []

	columns = [frappe.desk.query_report.get_column_as_dict(c) for c in columns]

	if report_name == "Stock Balance":
		if not _rows_have_field(data, "description"):
			_enrich_rows_with_description(data)

	if any(c.get("fieldname") == "description" for c in columns):
		columns = _move_column_after(columns, "description", "item_code")
	else:
		columns = _insert_column_after(columns, DESCRIPTION_COLUMN, "item_code")

	for fieldname in config.get("remove_columns", []):
		columns = [c for c in columns if c.get("fieldname") != fieldname]

	result["columns"] = columns
	result["result"] = data
	return result


def _rows_have_field(data: list, fieldname: str) -> bool:
	for row in data:
		if isinstance(row, dict):
			return fieldname in row
	return False


def _enrich_rows_with_description(data: list) -> None:
	if not data:
		return

	item_codes = list(
		{
			row.get("item_code")
			for row in data
			if isinstance(row, dict) and row.get("item_code")
		}
	)
	if not item_codes:
		return

	desc_map = {}
	chunk_size = 500
	for i in range(0, len(item_codes), chunk_size):
		chunk = item_codes[i : i + chunk_size]
		items = frappe.get_all(
			"Item",
			filters={"name": ["in", chunk]},
			fields=["name", "description"],
		)
		for item in items:
			desc_map[item["name"]] = item.get("description") or ""

	strip_html = frappe.utils.strip_html
	for row in data:
		if not isinstance(row, dict):
			continue
		raw = desc_map.get(row.get("item_code"), "")
		row["description"] = strip_html(raw) if raw else ""


def _insert_column_after(columns: list[dict], new_col: dict, after_fieldname: str) -> list[dict]:
	if any(c.get("fieldname") == new_col.get("fieldname") for c in columns):
		return columns

	result = []
	inserted = False
	for col in columns:
		result.append(col)
		if not inserted and col.get("fieldname") == after_fieldname:
			result.append(new_col)
			inserted = True

	if not inserted:
		result.insert(min(1, len(result)), new_col)

	return result


def _move_column_after(columns: list[dict], fieldname: str, after_fieldname: str) -> list[dict]:
	"""Move an existing column (by fieldname) to immediately after another column.

	If the target column or after-column doesn't exist, returns columns unchanged.
	"""
	col = None
	remaining = []
	for c in columns:
		if c.get("fieldname") == fieldname and col is None:
			col = c
		else:
			remaining.append(c)

	if not col:
		return columns

	result = []
	inserted = False
	for c in remaining:
		result.append(c)
		if not inserted and c.get("fieldname") == after_fieldname:
			result.append(col)
			inserted = True

	if not inserted:
		return columns

	return result
