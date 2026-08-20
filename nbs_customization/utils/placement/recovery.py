# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe

RECOVERY_FIELDS = [
	"cumulative_invoiced",
	"cumulative_collected",
	"outstanding_on_contract",
	"recovery_pct_invoiced",
	"recovery_pct_collected",
]


def recompute_contract_recovery(contract_name):
	contract = frappe.get_cached_doc("Instrument Placement Contract", contract_name)
	target = contract.total_recovery_target or 0

	invoices = frappe.db.get_all(
		"Sales Invoice",
		filters={
			"custom_instrument_placement_contract": contract_name,
			"custom_counts_toward_recovery": 1,
			"docstatus": 1,
		},
		fields=["grand_total", "outstanding_amount"],
	)

	cumulative_invoiced = sum((inv.grand_total or 0) for inv in invoices)
	cumulative_collected = sum(
		(inv.grand_total or 0) - (inv.outstanding_amount or 0) for inv in invoices
	)
	outstanding_on_contract = target - cumulative_collected

	recovery_pct_invoiced = (cumulative_invoiced / target * 100) if target else 0
	recovery_pct_collected = (cumulative_collected / target * 100) if target else 0

	for field, value in [
		("cumulative_invoiced", cumulative_invoiced),
		("cumulative_collected", cumulative_collected),
		("outstanding_on_contract", outstanding_on_contract),
		("recovery_pct_invoiced", recovery_pct_invoiced),
		("recovery_pct_collected", recovery_pct_collected),
	]:
		frappe.db.set_value(
			"Instrument Placement Contract",
			contract_name,
			field,
			value,
			update_modified=False,
		)

	return {
		"cumulative_invoiced": cumulative_invoiced,
		"cumulative_collected": cumulative_collected,
		"outstanding_on_contract": outstanding_on_contract,
		"recovery_pct_invoiced": recovery_pct_invoiced,
		"recovery_pct_collected": recovery_pct_collected,
	}
