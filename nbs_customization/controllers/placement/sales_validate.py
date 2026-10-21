# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from erpnext import get_company_currency
from erpnext.setup.utils import get_exchange_rate
from frappe.utils import flt

from nbs_customization.utils.placement.recovery import RECOVERABLE_TRANSACTION_TYPES
from nbs_customization.utils.placement.valid_items import validate_items_belong_to_analyzer


def validate_placement_transaction(doc, method=None):
	if not doc.get("custom_instrument_placement_contract"):
		return

	contract_name = doc.custom_instrument_placement_contract
	contract = frappe.get_cached_doc("Instrument Placement Contract", contract_name)
	return_source_contract = _get_return_source_contract(doc)

	if return_source_contract and return_source_contract != contract_name:
		frappe.throw(
			frappe._("Return contract {0} does not match the original document contract {1}.").format(
				frappe.bold(contract_name), frappe.bold(return_source_contract)
			)
		)
	if (
		contract.contract_status not in ("Active", "Ownership Pending")
		and return_source_contract != contract_name
	):
		frappe.throw(
			frappe._("Placement Contract {0} is not open (status: {1}).").format(
				frappe.bold(contract_name), frappe.bold(contract.contract_status)
			)
		)
	if doc.get("customer") and contract.customer and doc.customer != contract.customer:
		frappe.throw(
			frappe._("Invoice customer {0} does not match Contract {1} customer {2}.").format(
				frappe.bold(doc.customer),
				frappe.bold(contract_name),
				frappe.bold(contract.customer),
			)
		)

	ttype = doc.get("custom_placement_transaction_type")
	if not ttype:
		frappe.throw(
			frappe._("Placement Transaction Type is required when a Placement Contract is selected.")
		)

	# Spec membership governs stock reagents/consumables only. Service fees and
	# the analyzer asset itself are not spec lines.
	if ttype not in ("Ownership Transfer", "Shortfall Penalty"):
		codes = [item.item_code for item in doc.items if item.item_code]
		stock_codes = (
			set(frappe.db.get_all("Item", filters={"name": ("in", codes), "is_stock_item": 1}, pluck="name"))
			if codes
			else set()
		)
		validate_items_belong_to_analyzer(
			contract.analyzer_pid, [c for c in codes if c in stock_codes], throw=True
		)

	_validate_transaction_type_consistency(ttype, contract.contract_type)
	_validate_contract_rates(doc, contract, ttype)

	if doc.doctype == "Sales Invoice":
		doc.custom_counts_toward_recovery = 1 if ttype in RECOVERABLE_TRANSACTION_TYPES else 0


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


def _validate_contract_rates(doc, contract, ttype):
	if doc.get("is_return") or ttype not in (
		"Contract Reagent Sale",
		"Contract Consumable Replenishment",
	):
		return
	rates = {
		line.item_code: flt(line.contract_price)
		for line in contract.contract_reagent_lines
		if line.item_code and flt(line.contract_price) > 0
	}
	for line in doc.get("items"):
		contract_rate = rates.get(line.item_code)
		if not contract_rate:
			continue
		contract_rate = _contract_rate_in_company_currency(contract, contract_rate, doc)
		if contract_rate is None:
			continue
		line_rate = _company_rate_per_stock_uom(doc, line)
		if line_rate < contract_rate - 0.01:
			frappe.throw(
				frappe._("Item {0} rate {1} is below the contracted rate {2}.").format(
					frappe.bold(line.item_code), line_rate, contract_rate
				)
			)


def _company_rate_per_stock_uom(doc, line):
	conversion_factor = flt(line.get("conversion_factor")) or 1
	base_rate = flt(line.get("base_rate"))
	if not base_rate:
		base_rate = flt(line.get("rate")) * flt(doc.get("conversion_rate") or 1)
	return base_rate / conversion_factor


def _contract_rate_in_company_currency(contract, rate, doc):
	company = contract.get("company") or doc.get("company")
	company_currency = get_company_currency(company)
	price_list = contract.get("contract_price_list")
	price_list_currency = (
		frappe.db.get_value("Price List", price_list, "currency") if price_list else company_currency
	)
	if not price_list_currency or price_list_currency == company_currency:
		return rate
	exchange_rate = get_exchange_rate(
		price_list_currency,
		company_currency,
		doc.get("posting_date") or doc.get("transaction_date"),
	)
	if not exchange_rate:
		return None
	return rate * exchange_rate


def _get_return_source_contract(doc):
	if not doc.get("is_return"):
		return None
	source_name = doc.get("return_against")
	if not source_name:
		return None
	source = frappe.db.get_value(
		doc.doctype,
		source_name,
		["docstatus", "custom_instrument_placement_contract"],
		as_dict=True,
	)
	if not source or source.docstatus != 1:
		return None
	return source.custom_instrument_placement_contract


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
