import frappe

from nbs_customization.utils.placement.recovery import (
	RECOVERABLE_TRANSACTION_TYPES,
	recompute_contract_recovery,
)


def execute():
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
