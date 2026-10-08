# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from math import ceil

import frappe
from frappe.model.document import Document


class ContractAmendment(Document):
	def on_submit(self):
		self.status = "Pending Customer Signature"
		self.db_set("status", "Pending Customer Signature")

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

		if self.new_pricing_worksheet:
			_remap_lines_from_worksheet(contract, self.new_pricing_worksheet)

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

		# Recompute derived economics explicitly: post-submit saves skip
		# validate, so without this the stored snapshot keeps pre-amendment
		# values. An explicit new_min_value still wins over the recompute.
		contract._compute_min_monthly_value()
		contract._compute_cpt_fields()
		if self.new_min_value:
			contract.min_monthly_value = self.new_min_value

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
			ws_type = frappe.db.get_value(
				"Instrument Pricing Worksheet", self.new_pricing_worksheet, "contract_type"
			)
			if ws_type and ws_type != contract.contract_type:
				frappe.throw(
					frappe._("Worksheet type {0} does not match contract type {1}.").format(
						ws_type, contract.contract_type
					)
				)


def _remap_lines_from_worksheet(contract, ws_name):
	"""Rebuild contract mirrors from a newly linked worksheet.

	Same mapping as make_instrument_placement_contract, applied to a saved
	contract. Explicit amendment overrides are applied afterwards by the
	caller, so a negotiated figure still wins over the recompute.
	"""
	from frappe.utils import flt

	ws = frappe.get_doc("Instrument Pricing Worksheet", ws_name)
	if ws.docstatus != 1:
		frappe.throw(frappe._("Worksheet {0} must be submitted before applying.").format(ws_name))
	old_ws = contract.pricing_worksheet
	contract.pricing_worksheet = ws.name
	contract.total_recovery_target = ws.final_revenue_target
	contract.avg_samples_per_day = ws.avg_samples_per_day
	contract.operational_days_per_month = ws.operational_days_per_month
	contract.revenue_share_pct = ws.required_revenue_share_pct if ws.contract_type == "CPT" else 0
	contract.set("contract_reagent_lines", [])
	for src in ws.reagent_lines:
		contract.append(
			"contract_reagent_lines",
			{
				"item_code": src.item_code,
				"test_parameter": src.test_parameter,
				"uom": frappe.db.get_value("Item", src.item_code, "stock_uom"),
				"standard_price": src.cogs_per_pack,
				"contract_price": src.selling_price_per_pack or 0,
				"qty_required_total": src.packs_needed or 0,
				"min_monthly_qty": ceil(flt(src.monthly_test_volume) / flt(src.tests_per_pack))
				if flt(src.tests_per_pack)
				else 0,
				"cogs_per_unit": src.cogs_per_pack,
				"monthly_test_volume": src.monthly_test_volume,
				"pack_volume_ml": src.pack_volume_ml,
				"bg_consumption_ml_day": src.bg_consumption_ml_day,
				"bg_consumption_ml_month": src.bg_consumption_ml_month,
				"consumption_ml_per_test": src.consumption_ml_per_test,
				"total_consumption_ml_month": src.total_consumption_ml_month,
				"agreed_test_price": src.price_per_test or 0,
			},
		)
	contract.set("contract_consumable_lines", [])
	for src in ws.consumable_lines:
		contract.append(
			"contract_consumable_lines",
			{
				"item_code": src.item_code,
				"uom": frappe.db.get_value("Item", src.item_code, "stock_uom"),
				"standard_price": src.cogs_per_unit,
				"contract_price": 0,
				"qty_required_total": src.total_units_over_term or 0,
				"cogs_per_unit": src.cogs_per_unit,
			},
		)
	if old_ws and old_ws != ws.name:
		old = frappe.get_doc("Instrument Pricing Worksheet", old_ws)
		old.db_set("status", "Approved")
		old.db_set("linked_contract", None)
	ws.db_set("status", "Applied to Contract")
	ws.db_set("linked_contract", contract.name)
