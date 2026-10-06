# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Stock-to-Asset capitalization shared by worksheet and placement contract."""

import frappe
from frappe import _


def company_store_location_name(company):
	"""Store Location name for *company*, derived from its abbreviation."""
	abbr = frappe.db.get_value("Company", company, "abbr") or company
	return f"{abbr} - Store"


def get_company_store_location(company=None):
	"""Return the company store Location name, or None if not seeded yet."""
	company = company or _resolve_company()
	if not company:
		return None
	name = company_store_location_name(company)
	return name if frappe.db.exists("Location", name) else None


def _resolve_company():
	return frappe.defaults.get_defaults().get("company") or frappe.db.get_value("Company", {}, "name")


def capitalize_serial_for_placement(
	customer: str,
	customer_name: str | None,
	analyzer_pid: str,
	warehouse: str,
	serial_no: str,
):
	"""Consume one serialized analyzer from stock into a placement Asset.

	Returns the Asset name. The Asset starts at the company store with
	Warehouse status; deployment moves it to the customer site later.
	Linking to a contract happens at contract submit.
	"""
	if not serial_no:
		raise frappe.ValidationError(_("A Serial No is required to capitalize an analyzer for placement."))
	if not frappe.db.get_value("Item", analyzer_pid, "has_serial_no"):
		raise frappe.ValidationError(
			_("Analyzer Item {0} must have Serial No tracking enabled (has_serial_no=1).").format(
				analyzer_pid
			)
		)

	serial_doc = frappe.get_doc("Serial No", serial_no)
	if serial_doc.item_code != analyzer_pid:
		raise frappe.ValidationError(
			_("Serial No {0} does not match analyzer {1}.").format(serial_no, analyzer_pid)
		)
	if serial_doc.status != "Active" or serial_doc.warehouse != warehouse:
		raise frappe.ValidationError(
			_("Serial No {0} is not available in warehouse {1}.").format(serial_no, warehouse)
		)

	capital_item = "Capital Asset"
	if not frappe.db.exists("Item", capital_item):
		raise frappe.ValidationError(
			_("Capital asset item '{0}' not found. Run migrate to create it.").format(capital_item)
		)

	company = _resolve_company()

	asset_category = frappe.db.get_value("Item", capital_item, "asset_category")
	if not asset_category:
		raise frappe.ValidationError(
			_("Item {0} has no Asset Category set. Set one on the Item master.").format(capital_item)
		)

	instrument_spec = frappe.db.get_value("Item", analyzer_pid, "custom_instrument_specification")

	asset = frappe.get_doc(
		{
			"doctype": "Asset",
			"asset_name": "{0} - {1}".format(customer_name or customer, serial_doc.serial_no),
			"item_code": capital_item,
			"company": company,
			"asset_category": asset_category,
			"location": _resolve_asset_location(company),
			"custom_serial_no": serial_no,
			"custom_instrument_specification": instrument_spec,
			"custom_current_deployment_status": "Warehouse",
			"gross_purchase_amount": serial_doc.purchase_rate or 0,
			"net_purchase_amount": serial_doc.purchase_rate or 0,
			"purchase_date": frappe.utils.today(),
			"available_for_use_date": frappe.utils.today(),
			"asset_type": "Composite Asset",
		}
	).insert(ignore_permissions=True)

	cap = frappe.get_doc(
		{
			"doctype": "Asset Capitalization",
			"company": company,
			"target_item_code": capital_item,
			"target_asset": asset.name,
			"posting_date": frappe.utils.today(),
			"stock_items": [
				{
					"item_code": analyzer_pid,
					"warehouse": warehouse,
					"stock_qty": 1,
					"use_serial_batch_fields": 1,
					"serial_no": serial_doc.serial_no,
				}
			],
		}
	)
	cap.insert(ignore_permissions=True)
	cap.submit()

	asset.reload()
	asset.submit()

	return asset.name


def _resolve_asset_location(company):
	"""Company store first; any existing Location as back-compat fallback."""
	store = get_company_store_location(company)
	if store:
		return store
	fallback = frappe.db.get_value("Location", {}, "name")
	if not fallback:
		raise frappe.ValidationError(_("No Location found — create one before capitalizing an analyzer."))
	return fallback
