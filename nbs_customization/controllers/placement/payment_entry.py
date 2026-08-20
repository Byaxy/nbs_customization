# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


def get_placement_contracts_from_references(doc):
	contracts = set()
	for ref in doc.get("references") or []:
		if ref.reference_doctype != "Sales Invoice":
			continue
		contract = frappe.db.get_value(
			"Sales Invoice",
			ref.reference_name,
			"custom_instrument_placement_contract",
		)
		if contract:
			contracts.add(contract)
	return list(contracts)


def on_submit(doc, method=None):
	for contract_name in get_placement_contracts_from_references(doc):
		recompute_contract_recovery(contract_name)


def on_cancel(doc, method=None):
	for contract_name in get_placement_contracts_from_references(doc):
		recompute_contract_recovery(contract_name)
