# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, getdate

from nbs_customization.utils.placement.periods import (
	period_end,
	period_start,
	posting_date_for_period,
	validate_period,
)
from nbs_customization.utils.placement.permissions import (
	FINANCE_MANAGERS,
	require_contract_access,
	require_roles,
)
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


class MonthlyReconciliation(Document):
	def validate(self):
		self._validate_contract()
		self._update_contract_breach_count()
		self._update_contract_recovery()

	def _validate_contract(self):
		contract = frappe.get_doc("Instrument Placement Contract", self.contract)
		if contract.contract_type not in ("RRA", "RLO"):
			frappe.throw(frappe._("Monthly Reconciliation is only for RRA/RLO contracts."))
		if contract.contract_status != "Active":
			frappe.throw(
				frappe._("Monthly Reconciliation requires an Active contract (current: {0}).").format(
					contract.contract_status
				)
			)

	def on_submit(self):
		self.reconciliation_status = "Verified"
		self.db_set("reconciliation_status", "Verified")

	def _update_contract_breach_count(self):
		# Do not let regeneration of an older period overwrite a newer count.
		if frappe.db.exists(
			"Monthly Reconciliation",
			{"contract": self.contract, "period": (">", self.period), "name": ("!=", self.name)},
		):
			return
		frappe.db.set_value(
			"Instrument Placement Contract",
			self.contract,
			"consecutive_breach_count",
			self.consecutive_breach_count or 0,
		)

	def _update_contract_recovery(self):
		recompute_contract_recovery(self.contract)


@frappe.whitelist()
def generate_monthly_reconciliation(contract_name, period):
	validate_period(period)
	require_roles(*FINANCE_MANAGERS)
	require_contract_access(contract_name, "write")
	contract = frappe.get_doc("Instrument Placement Contract", contract_name)
	if contract.contract_type not in ("RRA", "RLO"):
		frappe.throw(frappe._("Monthly Reconciliation is only for RRA/RLO contracts."))
	if contract.contract_status != "Active":
		frappe.throw(
			frappe._("Monthly Reconciliation requires an Active contract (current: {0}).").format(
				contract.contract_status
			)
		)

	existing = frappe.db.get_value(
		"Monthly Reconciliation",
		{"contract": contract_name, "period": period},
		"name",
	)
	if existing:
		mrc = frappe.get_doc("Monthly Reconciliation", existing)
		if mrc.docstatus == 1:
			frappe.throw(
				frappe._("Monthly Reconciliation {0} is already submitted.").format(frappe.bold(mrc.name))
			)
	else:
		mrc = frappe.get_doc(
			{
				"doctype": "Monthly Reconciliation",
				"contract": contract_name,
				"period": period,
				"period_start": period_start(period),
				"period_end": period_end(period),
			}
		)
		mrc.insert(ignore_permissions=True)

	invoices = frappe.db.get_all(
		"Sales Invoice",
		filters={
			"custom_instrument_placement_contract": contract_name,
			"custom_placement_transaction_type": (
				"in",
				[
					"Contract Reagent Sale",
					"Contract Consumable Replenishment",
				],
			),
			"posting_date": ("between", [mrc.period_start, mrc.period_end]),
			"docstatus": 1,
		},
		fields=["name", "posting_date", "grand_total", "custom_placement_transaction_type"],
	)

	mrc.linked_invoices = []
	for inv in invoices:
		mrc.append(
			"linked_invoices",
			{
				"sales_invoice": inv.name,
				"invoice_date": inv.posting_date,
				"invoice_amount": inv.grand_total,
				"placement_transaction_type": inv.custom_placement_transaction_type,
			},
		)

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


def _compute_compliance(mrc, contract, total_actual):
	min_required = contract.min_monthly_value or 0
	previous_breach_count = _previous_breach_count(mrc, contract)
	mrc.previous_breach_count = previous_breach_count

	if total_actual >= min_required:
		mrc.compliance_status = "Compliant"
		mrc.consecutive_breach_count = 0
		return

	grace = contract.grace_period_days or 0
	if grace > 0:
		grace_deadline = add_days(mrc.period_end, grace)
		if getdate(frappe.utils.today()) <= getdate(grace_deadline):
			mrc.compliance_status = "Grace Period"
			mrc.consecutive_breach_count = previous_breach_count
			return

	mrc.compliance_status = "Shortfall"
	new_count = previous_breach_count + 1
	mrc.consecutive_breach_count = new_count

	if contract.breach_threshold and new_count >= contract.breach_threshold:
		_auto_create_repossession_request(mrc, contract)


def _previous_breach_count(mrc, contract):
	prior = frappe.db.get_all(
		"Monthly Reconciliation",
		filters={
			"contract": contract.name,
			"period": ("<", mrc.period),
			"name": ("!=", mrc.name or ""),
		},
		fields=["consecutive_breach_count"],
		order_by="period desc",
		limit=1,
	)
	if prior:
		return prior[0].consecutive_breach_count or 0
	# Regeneration of an existing period keeps its earlier baseline.
	if mrc.compliance_status and mrc.previous_breach_count is not None:
		return mrc.previous_breach_count or 0
	return contract.consecutive_breach_count or 0


@frappe.whitelist()
def create_penalty_invoice(reconciliation_name):
	require_roles(*FINANCE_MANAGERS)
	mrc = frappe.get_doc("Monthly Reconciliation", reconciliation_name)
	require_contract_access(mrc.contract, "write")

	if mrc.compliance_status not in ("Shortfall", "Breach"):
		frappe.throw(
			frappe._(
				"Penalty invoices can only be created for reconciliations "
				"with Shortfall or Breach compliance status."
			)
		)

	if mrc.penalty_invoice:
		frappe.throw(
			frappe._("Penalty Invoice {0} already exists for this reconciliation.").format(
				mrc.penalty_invoice
			)
		)

	contract = frappe.get_doc("Instrument Placement Contract", mrc.contract)
	penalty_amount = _resolve_penalty_amount(contract, mrc.shortfall_value)
	posting_date = posting_date_for_period(mrc.period)
	company = contract.company or frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		frappe.throw(frappe._("Set a default Company before creating a penalty invoice."))

	# Site mandates SO links on SI items — bill the penalty against its own order.
	penalty_order = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": company,
			"customer": contract.customer,
			"transaction_date": posting_date,
			"delivery_date": posting_date,
			"custom_instrument_placement_contract": contract.name,
			"custom_placement_transaction_type": "Shortfall Penalty",
			"items": [
				{
					"item_code": "SHORTFALL-PENALTY",
					"qty": 1,
					"rate": penalty_amount,
				}
			],
		}
	)
	penalty_order.insert(ignore_permissions=True)
	penalty_order.submit()
	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": contract.customer,
			"custom_instrument_placement_contract": contract.name,
			"custom_placement_transaction_type": "Shortfall Penalty",
			"custom_counts_toward_recovery": 0,
			"posting_date": posting_date,
			"set_posting_time": 1,
			"items": [
				{
					"item_code": "SHORTFALL-PENALTY",
					"qty": 1,
					"rate": penalty_amount,
					"sales_order": penalty_order.name,
					"so_detail": penalty_order.items[0].name,
				}
			],
		}
	)
	si.insert(ignore_permissions=True)
	si.submit()

	mrc.db_set("penalty_invoice", si.name)

	frappe.msgprint(frappe._("Penalty Invoice {0} created successfully.").format(frappe.bold(si.name)))

	return si.name


def _resolve_penalty_amount(contract, shortfall):
	penalty_type = contract.shortfall_penalty_type
	value = contract.penalty_value or 0
	if penalty_type == "Fixed Amount":
		amount = value
	elif penalty_type == "Percentage of Shortfall":
		amount = (shortfall or 0) * value / 100
	else:
		frappe.throw(
			frappe._(
				"Contract {0} has no shortfall penalty configured. "
				"Set 'Fixed Amount' or 'Percentage of Shortfall' first."
			).format(frappe.bold(contract.name))
		)
	if amount <= 0:
		frappe.throw(frappe._("Penalty amount must be greater than zero."))
	return amount


def _auto_create_repossession_request(mrc, contract):
	if contract.contract_status != "Active":
		return
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
		{"contract": contract.name, "deployment_status": ("in", ("Deployed", "Under Service"))},
		"name",
	)
	if not deployment:
		return

	rr = frappe.get_doc(
		{
			"doctype": "Repossession Request",
			"contract": contract.name,
			"contract_type": contract.contract_type,
			"analyzer_deployment": deployment,
			"asset": contract.asset,
			"customer": contract.customer,
			"customer_name": contract.customer_name,
			"reason": "Minimum Purchase Breach",
			"breach_count": mrc.consecutive_breach_count,
			"months_breached": mrc.consecutive_breach_count,
			"outstanding_balance": contract.outstanding_on_contract,
			"requested_by": frappe.session.user,
			"request_date": frappe.utils.today(),
			"status": "Draft",
		}
	)
	rr.insert(ignore_permissions=True)
	frappe.msgprint(
		frappe._(
			"Repossession Request {0} has been auto-created for Contract {1} due to breach threshold reached."
		).format(frappe.bold(rr.name), frappe.bold(contract.name))
	)
