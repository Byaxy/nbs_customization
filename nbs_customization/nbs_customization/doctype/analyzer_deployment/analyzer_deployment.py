# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

ALLOWED_TRANSITIONS = {
	"Draft": {"Deployed", "Under Service"},
	"Deployed": {"Under Service", "Temporarily Retrieved", "Permanently Retrieved"},
	"Under Service": {"Deployed", "Temporarily Retrieved", "Permanently Retrieved"},
	"Temporarily Retrieved": {"Deployed", "Permanently Retrieved"},
	"Permanently Retrieved": set(),
}


class AnalyzerDeployment(Document):
	def validate(self):
		if not self.asset_storage_location:
			from nbs_customization.utils.placement.assets import get_company_store_location

			company = None
			if self.asset:
				company = frappe.db.get_value("Asset", self.asset, "company")
			self.asset_storage_location = get_company_store_location(company)
		self._validate_deployment()
		self._detect_status_transition()

	def _validate_deployment(self):
		if not self.contract or not self.asset:
			return
		asset_status = frappe.db.get_value("Asset", self.asset, ["docstatus", "status"], as_dict=True)
		if not asset_status or asset_status.docstatus != 1:
			frappe.throw(frappe._("Asset {0} must be submitted.").format(frappe.bold(self.asset)))
		if asset_status.status in ("Sold", "Scrapped", "Cancelled"):
			frappe.throw(
				frappe._("Asset {0} is {1} and cannot be deployed.").format(
					frappe.bold(self.asset), frappe.bold(asset_status.status)
				)
			)

		old = self.get_doc_before_save()
		existing_active = old and old.deployment_status in (
			"Deployed",
			"Under Service",
			"Temporarily Retrieved",
		)
		if self.deployment_status in ("Deployed", "Under Service"):
			contract_status = frappe.db.get_value(
				"Instrument Placement Contract", self.contract, "contract_status"
			)
			allowed_statuses = ("Active", "Ownership Pending") if existing_active else ("Active",)
			if contract_status not in allowed_statuses:
				frappe.throw(
					frappe._("Contract {0} must be Active before deployment (current: {1}).").format(
						frappe.bold(self.contract), frappe.bold(contract_status)
					)
				)

		was_permanently_retrieved = old and old.deployment_status == "Permanently Retrieved"
		if (
			self.deployment_status == "Permanently Retrieved"
			and not was_permanently_retrieved
			and not self.flags.allow_permanent_retrieval
		):
			frappe.throw(
				frappe._("Permanently Retrieved can only be set through Repossession or Ownership Transfer.")
			)

		if self.deployment_status in ("Deployed", "Under Service", "Temporarily Retrieved"):
			self._assert_no_other_active_deployment()

	def _assert_no_other_active_deployment(self):
		active_statuses = ("Deployed", "Under Service", "Temporarily Retrieved")
		other_asset = frappe.db.get_value(
			"Analyzer Deployment",
			{
				"asset": self.asset,
				"deployment_status": ("in", active_statuses),
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if other_asset:
			frappe.throw(
				frappe._("Asset {0} already has active deployment {1}.").format(
					frappe.bold(self.asset), frappe.bold(other_asset)
				)
			)
		other_contract = frappe.db.get_value(
			"Analyzer Deployment",
			{
				"contract": self.contract,
				"deployment_status": ("in", active_statuses),
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if other_contract:
			frappe.throw(
				frappe._("Contract {0} already has active deployment {1}.").format(
					frappe.bold(self.contract), frappe.bold(other_contract)
				)
			)

	def _detect_status_transition(self):
		new_status = self.deployment_status
		if self.is_new():
			if new_status == "Deployed":
				self._on_deployed()
			return

		old = self.get_doc_before_save()
		if not old:
			return

		old_status = old.deployment_status
		if new_status == old_status:
			return
		if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
			frappe.throw(
				frappe._("Cannot move Analyzer Deployment from '{0}' to '{1}'.").format(
					frappe.bold(old_status), frappe.bold(new_status)
				)
			)

		handlers = {
			"Deployed": self._on_deployed,
			"Under Service": self._on_under_service,
			"Temporarily Retrieved": self._on_retrieved,
			"Permanently Retrieved": self._on_permanently_retrieved,
		}

		handler = handlers.get(new_status)
		if handler:
			handler(old_status=old_status)

	def _on_deployed(self, old_status=None):
		frappe.db.set_value(
			"Asset",
			self.asset,
			"custom_current_deployment_status",
			"Deployed",
		)
		frappe.db.set_value(
			"Asset",
			self.asset,
			"custom_current_placement_contract",
			self.contract,
		)
		# Assert the physical precondition explicitly: same-day movements tie
		# on transaction_date, so ERPNext's latest-location lookup is a coin
		# flip — the movement below validates source against this field.
		frappe.db.set_value("Asset", self.asset, "location", self.asset_storage_location)
		self._create_asset_movement(
			from_location=self.asset_storage_location,
			to_location=self.asset_location,
			purpose="Transfer",
		)

	def _on_under_service(self, old_status=None):
		frappe.db.set_value(
			"Asset",
			self.asset,
			"custom_current_deployment_status",
			"Under Service",
		)

	def _on_retrieved(self, old_status=None):
		frappe.db.set_value(
			"Asset",
			self.asset,
			"custom_current_deployment_status",
			"Warehouse",
		)

	def _on_permanently_retrieved(self, old_status=None):
		frappe.db.set_value(
			"Asset",
			self.asset,
			"custom_current_deployment_status",
			"Warehouse",
		)
		frappe.db.set_value(
			"Asset",
			self.asset,
			"custom_current_placement_contract",
			None,
		)
		# Same same-day-tie rationale as _on_deployed: assert the asset sits
		# at the deployment site before the return movement validates it.
		frappe.db.set_value("Asset", self.asset, "location", self.asset_location)
		self._create_asset_movement(
			from_location=self.asset_location,
			to_location=self.asset_storage_location,
			purpose="Transfer",
			transaction_date=self.retrieval_date or self.deployment_date,
		)

	def _create_asset_movement(
		self, from_location=None, to_location=None, purpose="Transfer", transaction_date=None
	):
		if not frappe.db.exists("Asset", self.asset):
			return

		movement = frappe.get_doc(
			{
				"doctype": "Asset Movement",
				"company": frappe.db.get_value("Asset", self.asset, "company"),
				"purpose": purpose,
				"transaction_date": transaction_date or self.deployment_date or frappe.utils.today(),
				"assets": [
					{
						"asset": self.asset,
						"source_location": from_location,
						"target_location": to_location,
					}
				],
			}
		)
		movement.insert(ignore_permissions=True)
		movement.submit()
		return movement
