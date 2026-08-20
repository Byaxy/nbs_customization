# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, add_months, add_days
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


class MonthlyReconciliation(Document):
	def validate(self):
		self._update_contract_breach_count()
		self._update_contract_recovery()

	def on_submit(self):
		self.reconciliation_status = "Verified"
		self.db_set("reconciliation_status", "Verified")

	def _update_contract_breach_count(self):
		if self.compliance_status == "Compliant":
			frappe.db.set_value(
				"Instrument Placement Contract",
				self.contract,
				"consecutive_breach_count",
				0,
			)
		elif self.consecutive_breach_count:
			frappe.db.set_value(
				"Instrument Placement Contract",
				self.contract,
				"consecutive_breach_count",
				self.consecutive_breach_count,
			)

	def _update_contract_recovery(self):
		recompute_contract_recovery(self.contract)


@frappe.whitelist()
def generate_monthly_reconciliation(contract_name, period):
	contract = frappe.get_doc("Instrument Placement Contract", contract_name)
	if contract.contract_type not in ("RRA", "RLO"):
		frappe.throw(
			frappe._("Monthly Reconciliation is only for RRA/RLO contracts.")
		)

	existing = frappe.db.get_value(
		"Monthly Reconciliation",
		{"contract": contract_name, "period": period},
		"name",
	)
	if existing:
		mrc = frappe.get_doc("Monthly Reconciliation", existing)
	else:
		mrc = frappe.get_doc({
			"doctype": "Monthly Reconciliation",
			"contract": contract_name,
			"period": period,
			"period_start": format_date_range_start(period),
			"period_end": format_date_range_end(period),
		})
		mrc.insert(ignore_permissions=True)

	invoices = frappe.db.get_all(
		"Sales Invoice",
		filters={
			"custom_instrument_placement_contract": contract_name,
			"custom_placement_transaction_type": ("in", [
				"Contract Reagent Sale", "Contract Consumable Replenishment",
			]),
			"posting_date": ("between", [mrc.period_start, mrc.period_end]),
			"docstatus": 1,
		},
		fields=["name", "posting_date", "grand_total",
				"custom_placement_transaction_type"],
	)

	mrc.linked_invoices = []
	for inv in invoices:
		mrc.append("linked_invoices", {
			"sales_invoice": inv.name,
			"invoice_date": inv.posting_date,
			"invoice_amount": inv.grand_total,
			"placement_transaction_type": inv.custom_placement_transaction_type,
		})

	reagent_value = sum(
		inv.grand_total
		for inv in invoices
		if inv.custom_placement_transaction_type == "Contract Reagent Sale"
	)
	consumable_value = sum(
		inv.grand_total
		for inv in invoices
		if inv.custom_placement_transaction_type == "Contract Consumable Replenishment"
	)
	total_actual = reagent_value + consumable_value

	mrc.actual_reagent_value = reagent_value
	mrc.actual_consumable_value = consumable_value
	mrc.total_actual_value = total_actual

	min_required = contract.min_monthly_value or 0
	mrc.minimum_value_required = min_required
	mrc.shortfall_value = max(0, min_required - total_actual)

	_compute_compliance(mrc, contract, total_actual)

	mrc.invoiced_this_period = total_actual

	mrc.save(ignore_permissions=True)

	return mrc.name


def format_date_range_start(period):
	parts = period.split("-")
	return getdate(f"{parts[0]}-{parts[1]}-01")


def format_date_range_end(period):
	start = format_date_range_start(period)
	return add_days(add_months(start, 1), -1)


def _compute_compliance(mrc, contract, total_actual):
	min_required = contract.min_monthly_value or 0

	if total_actual >= min_required:
		mrc.compliance_status = "Compliant"
		mrc.consecutive_breach_count = 0
		return

	grace = contract.grace_period_days or 0
	previous_breach_count = contract.consecutive_breach_count or 0

	if grace > 0:
		grace_deadline = add_days(mrc.period_end, grace)
		if frappe.utils.today() <= grace_deadline:
			mrc.compliance_status = "Grace Period"
			mrc.consecutive_breach_count = previous_breach_count
			return

	mrc.compliance_status = "Shortfall"
	new_count = previous_breach_count + 1
	mrc.consecutive_breach_count = new_count

	if contract.breach_threshold and new_count >= contract.breach_threshold:
		_auto_create_repossession_request(mrc, contract)


@frappe.whitelist()
def create_penalty_invoice(reconciliation_name):
	mrc = frappe.get_doc("Monthly Reconciliation", reconciliation_name)

	if mrc.compliance_status not in ("Shortfall", "Breach"):
		frappe.throw(
			frappe._(
				"Penalty invoices can only be created for reconciliations "
				"with Shortfall or Breach compliance status."
			)
		)

	if mrc.penalty_invoice:
		frappe.throw(
			frappe._(
				"Penalty Invoice {0} already exists for this reconciliation."
			).format(mrc.penalty_invoice)
		)

	contract = frappe.get_doc("Instrument Placement Contract", mrc.contract)

	penalty_amount = mrc.shortfall_value or 0
	if contract.shortfall_penalty_type == "Fixed":
		penalty_amount = contract.penalty_value or 0
	elif contract.shortfall_penalty_type == "Percentage":
		penalty_amount = mrc.shortfall_value * (contract.penalty_value or 0) / 100

	si = frappe.get_doc({
		"doctype": "Sales Invoice",
		"customer": contract.customer,
		"custom_instrument_placement_contract": contract.name,
		"custom_placement_transaction_type": "Shortfall Penalty",
		"posting_date": frappe.utils.today(),
		"items": [
			{
				"item_code": "SHORTFALL-PENALTY",
				"qty": 1,
				"rate": penalty_amount,
			}
		],
	})
	si.insert(ignore_permissions=True)

	mrc.db_set("penalty_invoice", si.name)

	frappe.msgprint(
		frappe._("Penalty Invoice {0} created successfully.").format(
			frappe.bold(si.name)
		)
	)

	return si.name


def _auto_create_repossession_request(mrc, contract):
	existing = frappe.db.get_value(
		"Repossession Request",
		{
			"contract": contract.name,
			"status": ("!=", "Closed"),
		},
		"name",
	)
	if existing:
		return

	deployment = frappe.db.get_value(
		"Analyzer Deployment",
		{"contract": contract.name, "deployment_status": "Deployed"},
		"name",
	)
	if not deployment:
		return

	rr = frappe.get_doc({
		"doctype": "Repossession Request",
		"contract": contract.name,
		"analyzer_deployment": deployment,
		"reason": "Minimum Purchase Breach",
		"breach_count": mrc.consecutive_breach_count,
		"months_breached": mrc.consecutive_breach_count,
		"requested_by": frappe.session.user,
		"request_date": frappe.utils.today(),
		"status": "Draft",
	})
	rr.insert(ignore_permissions=True)
	frappe.msgprint(
		frappe._(
			"Repossession Request {0} has been auto-created for Contract {1} "
			"due to breach threshold reached."
		).format(frappe.bold(rr.name), frappe.bold(contract.name))
	)
