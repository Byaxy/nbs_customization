# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Candidate search and transaction type detection for historical linking."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

PUBLIC_TYPES_BY_CONTRACT = {
	"RRA": {"Contract Reagent Sale", "Contract Consumable Replenishment"},
	"RLO": {"Contract Reagent Sale", "Contract Consumable Replenishment"},
	"CPT": {"Contract Free Issue", "Contract Consumable Free Issue"},
}
INTERNAL_TYPES = {"Shortfall Penalty", "Ownership Transfer"}
INTERNAL_ITEM_TYPES = {
	"REVENUE-SHARE-FEE": "Contract Reagent Sale",
	"SHORTFALL-PENALTY": "Shortfall Penalty",
}
DOCUMENT_CONFIG = {
	"Sales Order": {
		"date_field": "transaction_date",
		"item_doctype": "Sales Order Item",
	},
	"Sales Invoice": {
		"date_field": "posting_date",
		"item_doctype": "Sales Invoice Item",
		"return_field": "is_return",
	},
	"Delivery Note": {
		"date_field": "posting_date",
		"item_doctype": "Delivery Note Item",
		"return_field": "is_return",
	},
}
MAX_ROWS = 500


def get_sales_order_candidates(contract, search=None):
	if not frappe.has_permission("Sales Order", "read"):
		return []
	filters = {
		"docstatus": 1,
		"customer": contract.customer,
		"company": contract.company,
		"custom_instrument_placement_contract": ["is", "not set"],
	}
	if search:
		filters["name"] = ["like", f"%{search}%"]

	documents = frappe.get_list(
		"Sales Order",
		filters=filters,
		fields=[
			"name",
			"customer",
			"transaction_date",
			"grand_total",
			"custom_instrument_placement_contract",
			"custom_placement_transaction_type",
		],
		order_by="transaction_date desc, name desc",
		limit=MAX_ROWS,
	)
	if not documents:
		return []

	items_by_parent = _get_items_by_parent("Sales Order", "Sales Order Item", [doc.name for doc in documents])
	reagent_codes, consumable_codes, _price_by_code = contract_item_data(contract)
	rows = []
	for document in documents:
		items = items_by_parent.get(document.name, [])
		if not items:
			continue

		item_codes = [row.item_code for row in items if row.item_code]
		internal_type = get_internal_type(contract, item_codes)
		contract_matches = set(item_codes) & (reagent_codes | consumable_codes)
		if not contract_matches and not internal_type:
			continue

		allowed_items = reagent_codes | consumable_codes | set(INTERNAL_ITEM_TYPES) | {contract.analyzer_pid}
		invalid_items = [code for code in item_codes if code not in allowed_items]
		date_value = document.get("transaction_date")
		warnings = []
		if invalid_items:
			warnings.append(_("Non-contract item(s): {0}").format(", ".join(sorted(set(invalid_items)))))
		if internal_type and contract_matches:
			warnings.append(_("Document mixes contract and internal items."))
		if _is_mixed_contract_document(item_codes, reagent_codes, consumable_codes):
			warnings.append(_("Document mixes reagent and consumable items."))
		if getdate(date_value) > getdate(today()):
			warnings.append(_("Document date is in the future."))

		suggested_type = _suggest_type(contract, item_codes, items, internal_type)
		if not suggested_type and not invalid_items:
			warnings.append(_("Transaction type could not be detected."))

		rows.append(
			{
				"name": document.name,
				"date": str(date_value),
				"grand_total": flt(document.grand_total),
				"item_summary": _get_item_summary(items),
				"suggested_type": suggested_type,
				"warnings": warnings,
				"blocked": bool(
					invalid_items or getdate(date_value) > getdate(today()) or not suggested_type
				),
			}
		)
	return rows


def _get_items_by_parent(doctype, item_doctype, names):
	items = frappe.get_all(
		item_doctype,
		filters={"parent": ("in", names), "parenttype": doctype},
		fields=["parent", "item_code", "qty", "rate"],
	)
	result = {}
	for item in items:
		result.setdefault(item.parent, []).append(item)
	return result


def contract_item_data(contract):
	reagent_codes = {line.item_code for line in contract.contract_reagent_lines if line.item_code}
	consumable_codes = {line.item_code for line in contract.contract_consumable_lines if line.item_code}
	price_by_code = {}
	for line in list(contract.contract_reagent_lines) + list(contract.contract_consumable_lines):
		if line.item_code and line.contract_price:
			price_by_code[line.item_code] = flt(line.contract_price)
	return reagent_codes, consumable_codes, price_by_code


def get_internal_type(contract, item_codes):
	for code, transaction_type in INTERNAL_ITEM_TYPES.items():
		if code in item_codes:
			return transaction_type
	if contract.analyzer_pid and contract.analyzer_pid in item_codes:
		return "Ownership Transfer"
	return None


def _is_mixed_contract_document(item_codes, reagent_codes, consumable_codes):
	return bool(set(item_codes) & reagent_codes) and bool(set(item_codes) & consumable_codes)


def _suggest_type(contract, item_codes, items, internal_type):
	if internal_type:
		return internal_type

	reagent_codes, consumable_codes, _price_by_code = contract_item_data(contract)
	codes = set(item_codes)
	allowed_items = reagent_codes | consumable_codes
	if not codes or not codes <= allowed_items:
		return None

	zero_rates = all(flt(item.rate) == 0 for item in items)
	only_reagent = codes <= reagent_codes
	only_consumable = codes <= consumable_codes

	if contract.contract_type in ("RRA", "RLO"):
		if only_reagent and not zero_rates:
			return "Contract Reagent Sale"
		if only_consumable and not zero_rates:
			return "Contract Consumable Replenishment"
	elif contract.contract_type == "CPT":
		if only_reagent and zero_rates:
			return "Contract Free Issue"
		if only_consumable and zero_rates:
			return "Contract Consumable Free Issue"
	return None


def _get_item_summary(items):
	parts = []
	for item in items[:4]:
		parts.append(f"{item.item_code} x {flt(item.qty):g}")
	if len(items) > 4:
		parts.append("...")
	return ", ".join(parts)


def suggest_document_type(contract, doc):
	if doc.doctype not in DOCUMENT_CONFIG:
		return None
	items = doc.get("items", [])
	item_codes = [row.item_code for row in items if row.item_code]
	internal_type = get_internal_type(contract, item_codes)
	return _suggest_type(contract, item_codes, items, internal_type)
