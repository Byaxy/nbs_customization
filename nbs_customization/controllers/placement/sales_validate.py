# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe

from nbs_customization.utils.placement.valid_items import validate_items_belong_to_analyzer


def validate_placement_transaction(doc, method=None):
	if not doc.get("custom_instrument_placement_contract"):
		return

	contract_name = doc.custom_instrument_placement_contract
	contract = frappe.get_cached_doc("Instrument Placement Contract", contract_name)

	# Spec membership governs stock reagents/consumables only — contract-level
	# service fees (revenue share, shortfall penalty) are non-stock charges.
	codes = [item.item_code for item in doc.items if item.item_code]
	stock_codes = (
		set(frappe.db.get_all("Item", filters={"name": ("in", codes), "is_stock_item": 1}, pluck="name"))
		if codes
		else set()
	)
	validate_items_belong_to_analyzer(
		contract.analyzer_pid, [c for c in codes if c in stock_codes], throw=True
	)

	ttype = doc.get("custom_placement_transaction_type")
	if not ttype:
		frappe.throw(
			frappe._("Placement Transaction Type is required when a Placement Contract is selected.")
		)

	_validate_transaction_type_consistency(ttype, contract.contract_type)


def _validate_transaction_type_consistency(ttype, contract_type):
	if ttype in ("Contract Free Issue", "Contract Consumable Free Issue"):
		if contract_type != "CPT":
			frappe.throw(
				frappe._(
					"Transaction type '{0}' is only valid for CPT contracts. This contract is {1}."
				).format(ttype, contract_type)
			)

	if contract_type == "CPT" and ttype not in (
		"Contract Free Issue",
		"Contract Consumable Free Issue",
		"Contract Reagent Sale",
		"Standard Sale",
	):
		frappe.throw(
			frappe._(
				"CPT contracts only allow 'Contract Free Issue', "
				"'Contract Consumable Free Issue', 'Contract Reagent Sale', or 'Standard Sale' transaction types."
			)
		)


def validate_free_issue_zero_rates(doc, method=None):
	ttype = doc.get("custom_placement_transaction_type")
	if ttype not in ("Contract Free Issue", "Contract Consumable Free Issue"):
		return
	for item in doc.items:
		if item.rate != 0:
			frappe.throw(
				frappe._("Item {0} has rate {1}. {2} lines must have rate=0.").format(
					frappe.bold(item.item_code),
					item.rate,
					ttype,
				)
			)
