import frappe
from frappe.utils import getdate, today

from nbs_customization.nbs_customization.doctype.monthly_reconciliation.monthly_reconciliation import (
	generate_monthly_reconciliation,
)
from nbs_customization.nbs_customization.doctype.revenue_share_statement.revenue_share_statement import (
	generate_revenue_share_statement,
)


def monthly_generate_reconciliations():
	contracts = frappe.get_all(
		"Instrument Placement Contract",
		filters={
			"contract_status": "Active",
			"contract_type": ("in", ("RRA", "RLO")),
		},
		pluck="name",
	)
	period = today()[:7]

	for name in contracts:
		try:
			generate_monthly_reconciliation(name, period)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Monthly Reconciliation Generation Failed for {name}",
			)


def monthly_generate_revenue_share():
	contracts = frappe.get_all(
		"Instrument Placement Contract",
		filters={
			"contract_status": "Active",
			"contract_type": "CPT",
		},
		pluck="name",
	)
	period = today()[:7]

	for name in contracts:
		try:
			generate_revenue_share_statement(name, period)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Revenue Share Generation Failed for {name}",
			)


def daily_process_amendments():
	amendments = frappe.get_all(
		"Contract Amendment",
		filters={
			"status": "Approved",
			"effective_date": ("<=", getdate(today())),
		},
		pluck="name",
	)

	for name in amendments:
		try:
			doc = frappe.get_doc("Contract Amendment", name)
			_apply_amendment_to_contract(doc)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Amendment Application Failed for {name}",
			)


def daily_check_rlo_ownership():
	eligible_contracts = frappe.db.sql(
		"""
		SELECT c.name
		FROM `tabInstrument Placement Contract` c
		WHERE c.contract_type = 'RLO'
		  AND c.contract_status = 'Active'
		  AND c.ownership_threshold_met = 1
		  AND NOT EXISTS (
			  SELECT 1
			  FROM `tabOwnership Transfer Request` otr
			  WHERE otr.contract = c.name
				AND otr.status != 'Closed'
		  )
		""",
		as_dict=True,
	)

	for row in eligible_contracts:
		try:
			from nbs_customization.nbs_customization.doctype.ownership_transfer_request.ownership_transfer_request import (
				create_ownership_transfer_request,
			)

			create_ownership_transfer_request(row.name)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Auto OTR Creation Failed for {row.name}",
			)


def _apply_amendment_to_contract(amendment):
	# Thin wrapper — logic lives on the controller (Phase 01 refactor).
	if isinstance(amendment, str):
		amendment = frappe.get_doc("Contract Amendment", amendment)
	amendment.apply_to_contract()
