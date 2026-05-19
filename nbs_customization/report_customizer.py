import frappe
from frappe import _

# Capture originals at module import time — before any override swap can occur.
# If captured inside a function body, the swap (_qr.run = run) would already be
# in effect, making _original_run point back to our own function → recursion.
import frappe.desk.query_report as _qr_module
from frappe.desk.query_report import run as _ORIGINAL_RUN
from frappe.desk.query_report import export_query as _ORIGINAL_EXPORT_QUERY


REPORT_CONFIG = {
	"Stock Balance": {
		"remove_columns": ["item_name"],
		"enrich_description": True,   # report SQL doesn't SELECT description
	},
	"Stock Ledger": {
		"remove_columns": ["item_name"],
		# Stock Ledger already SELECTs description — no enrichment needed
	},
	"Batch Item Expiry Status": {
		"remove_columns": ["item_name"],
		"enrich_description": True,   # report SQL doesn't SELECT description
		"item_code_field": "product",  # column fieldname is "product", not "item"
	},
	"Item Price Stock": {
		"remove_columns": ["item_name"],
		"enrich_description": True,   # report SQL doesn't SELECT description
	},
	"Batch-Wise Balance History": {
		"remove_columns": ["item_name"],
	},
	"Stock Projected Qty": {
		"remove_columns": ["item_name"],
	},
	"Stock Ageing": {
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
	Handles both normal report viewing AND export (when called via our export_query wrapper).
	"""
	result = _ORIGINAL_RUN(
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


@frappe.whitelist()
def export_query():
	"""Wrapper around frappe.desk.query_report.export_query.

	WHY THIS EXISTS
	---------------
	`override_whitelisted_methods` in hooks.py intercepts requests at the HTTP
	dispatcher level only. When `export_query` calls `run()` internally — as a
	direct Python reference inside the same module — the dispatcher is NOT
	involved, so our `run` override is completely bypassed.

	The result: on-screen report shows customised columns, but Excel / CSV
	exports the raw original columns (item_name present, description absent).

	THE FIX
	-------
	We also override `export_query` in hooks.py. Before delegating to the
	original function, we temporarily replace `frappe.desk.query_report.run`
	in the module's namespace with our patched version. Since Python resolves
	module-level names at call time (not at definition time), `export_query`
	will pick up our version when it calls `run(...)` internally.

	`try/finally` guarantees the original is always restored, even on error.

	THREAD / GEVENT SAFETY
	----------------------
	Each Gunicorn + gevent worker handles one request synchronously within a
	greenlet. There are no cooperative yield points between our two assignments
	(`_qr.run = run` and `_qr.run = _saved`), so no other greenlet can observe
	the temporary swap. The `finally` block also fires before control returns to
	the event loop, making this safe in production.
	"""
	_saved_run = _qr_module.run
	_qr_module.run = run  # inject our patched run into the module namespace
	try:
		return _ORIGINAL_EXPORT_QUERY()
	finally:
		_qr_module.run = _saved_run  # always restore, even on exception


# ---------------------------------------------------------------------------
# Core transformation — shared between run() and (indirectly) export_query()
# ---------------------------------------------------------------------------

def _apply_column_customizations(report_name: str, result: dict, config: dict) -> dict:
	columns = result.get("columns") or []
	data = result.get("result") or []

	columns = [frappe.desk.query_report.get_column_as_dict(c) for c in columns]

	if config.get("enrich_description") and not _rows_have_field(data, "description"):
		# Report SQL doesn't SELECT description — fetch and inject it from tabItem.
		# Some reports (e.g. Batch Item Expiry Status) key item code as "item"
		# rather than the standard "item_code" — allow per-report override.
		_enrich_rows_with_description(data, item_code_field=config.get("item_code_field", "item_code"))
	# Reports that already SELECT description (e.g. Stock Ledger) just need the
	# column repositioned below — the data rows already carry the value.

	# Use the same field name for column positioning as for data enrichment
	item_code_col_field = config.get("item_code_field", "item_code")
	if any(c.get("fieldname") == "description" for c in columns):
		# Already in columns (e.g. Stock Ledger): move to position after item code field
		columns = _move_column_after(columns, "description", item_code_col_field)
	else:
		# Not in columns (e.g. Stock Balance): insert after item code field
		columns = _insert_column_after(columns, DESCRIPTION_COLUMN, item_code_col_field)

	for fieldname in config.get("remove_columns", []):
		columns = [c for c in columns if c.get("fieldname") != fieldname]

	result["columns"] = columns
	result["result"] = data
	return result


# ---------------------------------------------------------------------------
# Data enrichment (Stock Balance only)
# ---------------------------------------------------------------------------

def _rows_have_field(data: list, fieldname: str) -> bool:
	for row in data:
		if isinstance(row, dict):
			return fieldname in row
	return False


def _enrich_rows_with_description(data: list, item_code_field: str = "item_code") -> None:
	if not data:
		return

	item_codes = list(
		{
			row.get(item_code_field)
			for row in data
			if isinstance(row, dict) and row.get(item_code_field)
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
		raw = desc_map.get(row.get(item_code_field), "")
		row["description"] = strip_html(raw) if raw else ""


# ---------------------------------------------------------------------------
# Column utilities
# ---------------------------------------------------------------------------

def _insert_column_after(columns: list[dict], new_col: dict, after_fieldname: str) -> list[dict]:
	"""Insert new_col immediately after the column with fieldname == after_fieldname."""
	if any(c.get("fieldname") == new_col.get("fieldname") for c in columns):
		return columns  # already present; don't double-insert

	result = []
	inserted = False
	for col in columns:
		result.append(col)
		if not inserted and col.get("fieldname") == after_fieldname:
			result.append(new_col)
			inserted = True

	if not inserted:
		# Fallback: put at index 1 (safe even for single-column lists)
		result.insert(min(1, len(result)), new_col)

	return result


def _move_column_after(columns: list[dict], fieldname: str, after_fieldname: str) -> list[dict]:
	"""Relocate an existing column to immediately after another column.

	Returns the original list unchanged if either column is not found.
	"""
	col_to_move = None
	remaining = []
	for c in columns:
		if c.get("fieldname") == fieldname and col_to_move is None:
			col_to_move = c
		else:
			remaining.append(c)

	if not col_to_move:
		return columns

	result = []
	inserted = False
	for c in remaining:
		result.append(c)
		if not inserted and c.get("fieldname") == after_fieldname:
			result.append(col_to_move)
			inserted = True

	return result if inserted else columns