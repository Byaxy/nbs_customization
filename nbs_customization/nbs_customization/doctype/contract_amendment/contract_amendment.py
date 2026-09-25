# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from math import ceil

import frappe
from frappe.model.document import Document


class ContractAmendment(Document):
	def apply_to_contract(self):
		"""Push approved terms onto the linked contract and flip Effective."""
		if self.status != "Approved":
			frappe.throw(
				frappe._("Amendment must be Approved before it can be applied (status is '{0}').").format(
					self.status
				)
			)
		contract = frappe.get_doc("Instrument Placement Contract", self.contract)
		self._validate_amendment_terms(contract)

		if self.new_declared_volume and contract.contract_reagent_lines:
			for line in contract.contract_reagent_lines:
				line.monthly_test_volume = self.new_declared_volume
				line.min_monthly_qty = ceil(
					self.new_declared_volume
					/ (
						(
							line.cogs_per_unit
							and frappe.db.get_value(
								"Reagent Specification", {"item": line.item_code}, "default_tests_per_pack"
							)
						)
						or 1
					)
				)

		if self.new_min_value:
			contract.min_monthly_value = self.new_min_value

		if self.new_share_pct:
			contract.revenue_share_pct = self.new_share_pct

		if self.new_pricing_worksheet:
			contract.pricing_worksheet = self.new_pricing_worksheet

		if self.new_recovery_target:
			contract.total_recovery_target = self.new_recovery_target

		# Amendments are the authorized mutation path for submitted contracts.
		contract.flags.ignore_validate_update_after_submit = True
		contract.save(ignore_permissions=True)

		self.status = "Effective"
		self.db_set("status", "Effective")

	def _validate_amendment_terms(self, contract):
		"""Guard history and worksheet eligibility before pushing terms."""
		if self.new_recovery_target and (contract.cumulative_collected or 0) > self.new_recovery_target:
			frappe.throw(
				frappe._(
					"New recovery target {0} is below cumulative collected {1} — history cannot be invalidated."
				).format(self.new_recovery_target, contract.cumulative_collected)
			)
		if self.new_pricing_worksheet:
			ws_status = frappe.db.get_value(
				"Instrument Pricing Worksheet", self.new_pricing_worksheet, "status"
			)
			if ws_status not in ("Approved", "Applied to Contract"):
				frappe.throw(
					frappe._(
						"Pricing Worksheet {0} has status '{1}' — only Approved worksheets apply."
					).format(self.new_pricing_worksheet, ws_status)
				)
			ws_analyzer = frappe.db.get_value(
				"Instrument Pricing Worksheet", self.new_pricing_worksheet, "analyzer_pid"
			)
			if ws_analyzer and ws_analyzer != contract.analyzer_pid:
				frappe.throw(
					frappe._("Worksheet analyzer {0} does not match contract analyzer {1}.").format(
						ws_analyzer, contract.analyzer_pid
					)
				)
