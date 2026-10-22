import frappe
from frappe.utils.fixtures import sync_fixtures

from nbs_customization.utils.placement.recovery import (
	RECOVERABLE_TRANSACTION_TYPES,
	recompute_contract_recovery,
)

REQUIRED_PLACEMENT_COLUMNS = (
	("Sales Invoice", "custom_instrument_placement_contract"),
	("Sales Invoice", "custom_placement_transaction_type"),
	("Sales Invoice", "custom_counts_toward_recovery"),
)


def execute():
	_ensure_placement_columns()
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"custom_instrument_placement_contract": ("is", "set"),
			"custom_placement_transaction_type": ("is", "set"),
		},
		fields=["name", "custom_placement_transaction_type", "custom_counts_toward_recovery"],
	)
	for invoice in invoices:
		expected = 1 if invoice.custom_placement_transaction_type in RECOVERABLE_TRANSACTION_TYPES else 0
		if invoice.custom_counts_toward_recovery != expected:
			frappe.db.set_value(
				"Sales Invoice",
				invoice.name,
				"custom_counts_toward_recovery",
				expected,
				update_modified=False,
			)

	contracts = frappe.get_all(
		"Instrument Placement Contract",
		filters={"docstatus": 1},
		pluck="name",
	)
	for contract in contracts:
		recompute_contract_recovery(contract)


def _ensure_placement_columns():
	"""Create the placement custom fields before querying them.

	post_model_sync patches run before fixture sync, so a site that has not
	synced this app's fixtures yet has no columns for these fields. Query
	information_schema directly because table columns are cached in Redis and
	that cache is not invalidated on DDL.
	"""
	missing = _missing_placement_columns()
	if not missing:
		return

	sync_fixtures("nbs_customization")

	missing = _missing_placement_columns()
	if missing:
		names = ", ".join(f"{doctype}.{column}" for doctype, column in missing)
		frappe.throw(f"Placement columns still missing after fixture sync: {names}")


def _missing_placement_columns():
	return [
		(doctype, column)
		for doctype, column in REQUIRED_PLACEMENT_COLUMNS
		if not frappe.db.sql(
			"SELECT 1 FROM information_schema.COLUMNS "
			"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
			(f"tab{doctype}", column),
		)
	]
