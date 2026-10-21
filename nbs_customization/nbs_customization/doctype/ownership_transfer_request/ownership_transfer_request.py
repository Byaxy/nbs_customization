# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from nbs_customization.utils.placement.permissions import (
	FINANCE_MANAGERS,
	PLACEMENT_MANAGERS,
	require_contract_access,
	require_roles,
)


class OwnershipTransferRequest(Document):
	def validate(self):
		if self.is_new():
			self._validate_contract_eligible()
		self._validate_status_permission()

	def before_submit(self):
		require_roles(*PLACEMENT_MANAGERS)

	def on_submit(self):
		self._validate_submit_requirements()
		self.status = "Pending Finance Review"
		self.db_set("status", "Pending Finance Review")

	def _validate_status_permission(self):
		old = self.get_doc_before_save()
		if not old or old.status == self.status:
			return
		if self.status == "Pending Legal Review":
			require_roles(*FINANCE_MANAGERS)
		elif self.status == "Approved":
			require_roles(*PLACEMENT_MANAGERS)
		elif self.status == "Transfer Completed" and not self.flags.allow_transfer_completed:
			frappe.throw(frappe._("Use 'Complete Transfer' to finish the ownership transfer."))

	def _validate_contract_eligible(self):
		contract = frappe.get_doc("Instrument Placement Contract", self.contract)
		if contract.contract_type != "RLO":
			frappe.throw(frappe._("Ownership Transfer is only available for RLO contracts."))
		if contract.contract_status not in ("Active", "Ownership Pending"):
			frappe.throw(
				frappe._("Contract {0} is not open for ownership transfer (status: {1}).").format(
					frappe.bold(self.contract), frappe.bold(contract.contract_status)
				)
			)
		if not contract.ownership_threshold_met:
			frappe.throw(
				frappe._(
					"Contract {0} is not eligible for ownership transfer — "
					"ownership threshold has not been met yet."
				).format(frappe.bold(self.contract))
			)
		if (contract.outstanding_on_contract or 0) > 1:
			frappe.throw(
				frappe._(
					"Contract {0} has outstanding balance {1}. All payments must be received before transfer."
				).format(
					frappe.bold(self.contract),
					frappe.bold(contract.outstanding_on_contract),
				)
			)
		if not contract.asset or not contract.serial_no:
			frappe.throw(
				frappe._("Contract {0} has no capitalized Asset with Serial No.").format(
					frappe.bold(self.contract)
				)
			)

	def _validate_submit_requirements(self):
		contract = frappe.get_doc("Instrument Placement Contract", self.contract)
		self.total_recovery_target = contract.total_recovery_target
		self.total_collected = contract.cumulative_collected
		self.outstanding_balance = contract.outstanding_on_contract

		worksheet = frappe.get_doc("Instrument Pricing Worksheet", contract.pricing_worksheet)
		self.analyzer_cost = worksheet.analyzer_landed_cost

		target = contract.total_recovery_target or 0
		collected = contract.cumulative_collected or 0
		if target:
			recovery_ratio = worksheet.analyzer_landed_cost / target
			self.analyzer_recovery_collected = collected * recovery_ratio
		else:
			self.analyzer_recovery_collected = 0

		nbv = frappe.db.get_value("Asset", self.asset, "value_after_depreciation") or 0
		self.net_book_value = nbv

		# Disposal gain/loss is the sale consideration less carrying value.
		# Recovery collected is a memo, not the asset sale proceeds.
		self.gain_loss = flt(self.transfer_price) - flt(nbv)

		# Persist the snapshot: in-memory assignment alone is discarded after
		# submit and poisons later saves (update-after-submit guard).
		for field in (
			"total_recovery_target",
			"total_collected",
			"outstanding_balance",
			"analyzer_cost",
			"analyzer_recovery_collected",
			"net_book_value",
			"gain_loss",
		):
			self.db_set(field, self.get(field))


@frappe.whitelist()
def create_ownership_transfer_request(contract_name):
	require_roles(*PLACEMENT_MANAGERS)
	require_contract_access(contract_name, "write")
	contract = frappe.get_doc("Instrument Placement Contract", contract_name)

	existing = frappe.db.get_value(
		"Ownership Transfer Request",
		{"contract": contract_name, "status": ("not in", ("Transfer Completed", "Closed"))},
		"name",
	)
	if existing:
		return existing

	deployment = frappe.db.get_value(
		"Analyzer Deployment",
		{"contract": contract_name, "deployment_status": ("in", ("Deployed", "Under Service"))},
		"name",
	)
	if not deployment:
		frappe.throw(
			frappe._("Contract {0} has no Deployed analyzer; transfer cannot start.").format(
				frappe.bold(contract_name)
			)
		)

	otr = frappe.get_doc(
		{
			"doctype": "Ownership Transfer Request",
			"contract": contract_name,
			"contract_type": contract.contract_type,
			"asset": contract.asset,
			"serial_no": contract.serial_no,
			"customer": contract.customer,
			"customer_name": contract.customer_name,
			"analyzer_deployment": deployment,
			"requested_by": frappe.session.user,
			"request_date": frappe.utils.today(),
			"transfer_price": 0,
			"status": "Draft",
		}
	)
	otr.insert(ignore_permissions=True)

	frappe.msgprint(
		frappe._("Ownership Transfer Request {0} created for Contract {1}.").format(
			frappe.bold(otr.name), frappe.bold(contract_name)
		)
	)

	return otr.name


@frappe.whitelist()
def complete_transfer(otr_name):
	require_roles(*FINANCE_MANAGERS)
	otr = frappe.get_doc("Ownership Transfer Request", otr_name)
	require_contract_access(otr.contract, "write")

	if otr.status != "Approved":
		frappe.throw(
			frappe._("Cannot complete transfer — status is '{0}', not 'Approved'.").format(otr.status)
		)

	if not otr.transfer_certificate:
		frappe.throw(frappe._("Transfer Certificate must be attached before completing the transfer."))
	if flt(otr.transfer_price) < 0:
		frappe.throw(frappe._("Transfer Price cannot be negative."))
	if not otr.asset or not otr.serial_no:
		frappe.throw(frappe._("Transfer requires the contract Asset and Serial No."))

	if not otr.transfer_date:
		otr.transfer_date = frappe.utils.today()

	deployment = frappe.db.get_value(
		"Analyzer Deployment",
		{"contract": otr.contract, "deployment_status": ("in", ("Deployed", "Under Service"))},
		"name",
	)
	if deployment:
		dep = frappe.get_doc("Analyzer Deployment", deployment)
		dep.deployment_status = "Permanently Retrieved"
		dep.flags.allow_permanent_retrieval = True
		dep.retrieval_reason = "Ownership Transfer"
		dep.retrieval_date = otr.transfer_date
		dep.ownership_transfer_request = otr.name
		dep.save(ignore_permissions=True)

	contract = frappe.get_doc("Instrument Placement Contract", otr.contract)
	si = _create_transfer_invoice(otr, contract)
	otr.db_set("transfer_invoice", si.name)

	frappe.db.set_value(
		"Instrument Placement Contract",
		otr.contract,
		{"contract_status": "Fulfilled", "termination_date": otr.transfer_date},
	)

	otr.status = "Transfer Completed"
	otr.db_set("status", "Transfer Completed")

	frappe.msgprint(
		frappe._("Ownership transfer completed for Contract {0}.").format(frappe.bold(otr.contract))
	)

	return otr.name


def _create_transfer_invoice(otr, contract):
	from erpnext.assets.doctype.asset.asset import make_sales_invoice

	company = frappe.db.get_value("Asset", otr.asset, "company") or contract.company
	if not company:
		frappe.throw(frappe._("Cannot determine the company for Asset {0}.").format(frappe.bold(otr.asset)))

	order = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": company,
			"customer": otr.customer,
			"transaction_date": otr.transfer_date,
			"delivery_date": otr.transfer_date,
			"custom_instrument_placement_contract": otr.contract,
			"custom_placement_transaction_type": "Ownership Transfer",
			"items": [
				{
					"item_code": contract.analyzer_pid,
					"qty": 1,
					"rate": flt(otr.transfer_price),
				}
			],
		}
	)
	order.flags.ignore_permissions = True
	order.insert(ignore_permissions=True)
	order.submit()

	si = make_sales_invoice(
		asset=otr.asset,
		item_code=contract.analyzer_pid,
		company=company,
		sell_qty=1,
		serial_no=otr.serial_no,
	)
	si.customer = otr.customer
	si.posting_date = otr.transfer_date
	si.set_posting_time = 1
	si.remarks = f"Ownership transfer for {otr.name}"
	si.custom_instrument_placement_contract = otr.contract
	si.custom_placement_transaction_type = "Ownership Transfer"
	si.custom_counts_toward_recovery = 0
	si.items[0].rate = flt(otr.transfer_price)
	si.items[0].price_list_rate = flt(otr.transfer_price)
	si.items[0].sales_order = order.name
	si.items[0].so_detail = order.items[0].name
	si.flags.ignore_permissions = True
	si.insert(ignore_permissions=True)
	si.submit()
	return si
