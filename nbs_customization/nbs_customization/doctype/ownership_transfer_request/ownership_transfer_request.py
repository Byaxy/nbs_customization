# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OwnershipTransferRequest(Document):
	def validate(self):
		if self.is_new():
			self._validate_contract_eligible()

	def on_submit(self):
		self._validate_submit_requirements()
		self.status = "Pending Finance Review"
		self.db_set("status", "Pending Finance Review")

	def _validate_contract_eligible(self):
		contract = frappe.get_doc("Instrument Placement Contract", self.contract)
		if contract.contract_type != "RLO":
			frappe.throw(
				frappe._("Ownership Transfer is only available for RLO contracts.")
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
					"Contract {0} has outstanding balance {1}. "
					"All payments must be received before transfer."
				).format(
					frappe.bold(self.contract),
					frappe.bold(contract.outstanding_on_contract),
				)
			)

	def _validate_submit_requirements(self):
		contract = frappe.get_doc("Instrument Placement Contract", self.contract)
		self.total_recovery_target = contract.total_recovery_target
		self.total_collected = contract.cumulative_collected
		self.outstanding_balance = contract.outstanding_on_contract

		worksheet = frappe.get_doc(
			"Instrument Pricing Worksheet", contract.pricing_worksheet
		)
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

		self.gain_loss = (self.analyzer_recovery_collected or 0) - nbv


@frappe.whitelist()
def create_ownership_transfer_request(contract_name):
	contract = frappe.get_doc("Instrument Placement Contract", contract_name)

	existing = frappe.db.get_value(
		"Ownership Transfer Request",
		{"contract": contract_name, "status": ("!=", "Closed")},
		"name",
	)
	if existing:
		return existing

	deployment = frappe.db.get_value(
		"Analyzer Deployment",
		{"contract": contract_name, "deployment_status": "Deployed"},
		"name",
	)

	otr = frappe.get_doc({
		"doctype": "Ownership Transfer Request",
		"contract": contract_name,
		"contract_type": contract.contract_type,
		"asset": contract.asset,
		"customer": contract.customer,
		"customer_name": contract.customer_name,
		"analyzer_deployment": deployment,
		"requested_by": frappe.session.user,
		"request_date": frappe.utils.today(),
		"status": "Draft",
	})
	otr.insert(ignore_permissions=True)

	frappe.msgprint(
		frappe._("Ownership Transfer Request {0} created for Contract {1}.").format(
			frappe.bold(otr.name), frappe.bold(contract_name)
		)
	)

	return otr.name


@frappe.whitelist()
def complete_transfer(otr_name):
	otr = frappe.get_doc("Ownership Transfer Request", otr_name)

	if otr.status != "Approved":
		frappe.throw(
			frappe._("Cannot complete transfer — status is '{0}', not 'Approved'.").format(
				otr.status
			)
		)

	if not otr.transfer_certificate:
		frappe.throw(
			frappe._("Transfer Certificate must be attached before completing the transfer.")
		)

	if not otr.transfer_date:
		otr.transfer_date = frappe.utils.today()

	deployment = frappe.db.get_value(
		"Analyzer Deployment",
		{"contract": otr.contract, "deployment_status": "Deployed"},
		"name",
	)
	if deployment:
		dep = frappe.get_doc("Analyzer Deployment", deployment)
		dep.deployment_status = "Permanently Retrieved"
		dep.retrieval_reason = "Ownership Transfer"
		dep.retrieval_date = otr.transfer_date
		dep.ownership_transfer_request = otr.name
		dep.save(ignore_permissions=True)

	frappe.db.set_value(
		"Instrument Placement Contract",
		otr.contract,
		"contract_status",
		"Fulfilled",
	)

	otr.status = "Transfer Completed"
	otr.db_set("status", "Transfer Completed")

	frappe.msgprint(
		frappe._("Ownership transfer completed for Contract {0}.").format(
			frappe.bold(otr.contract)
		)
	)

	return otr.name
