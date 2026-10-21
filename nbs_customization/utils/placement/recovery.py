# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt

RECOVERY_FIELDS = [
	"cumulative_invoiced",
	"cumulative_collected",
	"outstanding_on_contract",
	"recovery_pct_invoiced",
	"recovery_pct_collected",
]

RECOVERABLE_TRANSACTION_TYPES = (
	"Contract Reagent Sale",
	"Contract Consumable Replenishment",
)

NON_RECOVERABLE_TRANSACTION_TYPES = (
	"Contract Free Issue",
	"Contract Consumable Free Issue",
	"Shortfall Penalty",
	"Ownership Transfer",
)


def recompute_contract_recovery(contract_name):
	"""Rebuild recovery totals and RLO eligibility from submitted invoices.

	The transaction type is authoritative. The legacy manual flag stays as a
	fallback for invoices created before the flag became derived.
	"""
	contract = frappe.get_doc("Instrument Placement Contract", contract_name)
	target = flt(contract.total_recovery_target)

	invoices = frappe.db.get_all(
		"Sales Invoice",
		filters={
			"custom_instrument_placement_contract": contract_name,
			"docstatus": 1,
		},
		fields=[
			"grand_total",
			"outstanding_amount",
			"custom_placement_transaction_type",
			"custom_counts_toward_recovery",
		],
	)

	recoverable = [inv for inv in invoices if _counts_toward_recovery(inv)]
	cumulative_invoiced = sum(flt(inv.grand_total) for inv in recoverable)
	cumulative_collected = sum(flt(inv.grand_total) - flt(inv.outstanding_amount) for inv in recoverable)
	outstanding_on_contract = target - cumulative_collected

	recovery_pct_invoiced = (cumulative_invoiced / target * 100) if target else 0
	recovery_pct_collected = (cumulative_collected / target * 100) if target else 0

	values = {
		"cumulative_invoiced": cumulative_invoiced,
		"cumulative_collected": cumulative_collected,
		"outstanding_on_contract": outstanding_on_contract,
		"recovery_pct_invoiced": recovery_pct_invoiced,
		"recovery_pct_collected": recovery_pct_collected,
	}
	for field, value in values.items():
		frappe.db.set_value(
			"Instrument Placement Contract",
			contract_name,
			field,
			value,
			update_modified=False,
		)

	ownership_threshold_met = _is_rlo_ownership_eligible(
		contract.contract_type, target, cumulative_collected, outstanding_on_contract
	)
	if contract.contract_type == "RLO":
		frappe.db.set_value(
			"Instrument Placement Contract",
			contract_name,
			"ownership_threshold_met",
			1 if ownership_threshold_met else 0,
		)
		if ownership_threshold_met and contract.contract_status == "Active":
			frappe.db.set_value(
				"Instrument Placement Contract",
				contract_name,
				"contract_status",
				"Ownership Pending",
			)
	elif contract.contract_type in ("RRA", "CPT"):
		# RRA/CPT close when the recovery target is fully collected. RLO waits
		# for the ownership transfer so the asset is still on the books.
		if target and cumulative_collected >= target and contract.contract_status == "Active":
			frappe.db.set_value(
				"Instrument Placement Contract",
				contract_name,
				"contract_status",
				"Fulfilled",
			)

	return {
		**values,
		"ownership_threshold_met": ownership_threshold_met,
	}


def _counts_toward_recovery(invoice):
	transaction_type = invoice.custom_placement_transaction_type
	if transaction_type in RECOVERABLE_TRANSACTION_TYPES:
		return True
	if transaction_type in NON_RECOVERABLE_TRANSACTION_TYPES:
		return False
	return bool(invoice.custom_counts_toward_recovery)


def _is_rlo_ownership_eligible(contract_type, target, collected, outstanding):
	if contract_type != "RLO" or target <= 0:
		return False
	return collected >= target and outstanding <= 1
