# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReagentSpecification(Document):
	def validate(self):
		self._validate_percentages()
		if self.is_new() or not self.has_value_changed("reagent_role"):
			return
		self._validate_no_active_downstream_references()

	def _validate_percentages(self):
		for field in ("calibration_control_pct", "dead_volume_pct"):
			value = self.get(field)
			if value is not None and (value < 0 or value > 100):
				frappe.throw(frappe._("{0} must be between 0 and 100.").format(field))

	def _validate_no_active_downstream_references(self):
		item = self.item
		refs = []

		ipw_names = frappe.db.get_all(
			"Worksheet Test Reagent Line",
			filters={"item_code": item, "parenttype": "Instrument Pricing Worksheet"},
			pluck="parent",
			distinct=True,
		)
		if ipw_names:
			active_ipws = frappe.db.get_all(
				"Instrument Pricing Worksheet",
				filters=[
					["name", "in", ipw_names],
					["status", "!=", "Draft"],
				],
				pluck="name",
			)
			for name in active_ipws:
				refs.append(("Instrument Pricing Worksheet", name))

		ws_consumable_names = frappe.db.get_all(
			"Worksheet Consumable Line",
			filters={"item_code": item, "parenttype": "Instrument Pricing Worksheet"},
			pluck="parent",
			distinct=True,
		)
		if ws_consumable_names:
			active_consumable_ws = frappe.db.get_all(
				"Instrument Pricing Worksheet",
				filters=[
					["name", "in", ws_consumable_names],
					["status", "!=", "Draft"],
				],
				pluck="name",
			)
			for name in active_consumable_ws:
				refs.append(("Instrument Pricing Worksheet", name))

		crl_names = frappe.db.get_all(
			"Contract Test Reagent Line",
			filters={"item_code": item, "parenttype": "Instrument Placement Contract"},
			pluck="parent",
			distinct=True,
		)
		if crl_names:
			active_contracts = frappe.db.get_all(
				"Instrument Placement Contract",
				filters=[
					["name", "in", crl_names],
					["contract_status", "in", ["Active", "Fulfilled", "Breached"]],
				],
				pluck="name",
			)
			for name in active_contracts:
				refs.append(("Instrument Placement Contract", name))

		ccl_names = frappe.db.get_all(
			"Contract Consumable Line",
			filters={"item_code": item, "parenttype": "Instrument Placement Contract"},
			pluck="parent",
			distinct=True,
		)
		if ccl_names:
			active_contracts2 = frappe.db.get_all(
				"Instrument Placement Contract",
				filters=[
					["name", "in", ccl_names],
					["contract_status", "in", ["Active", "Fulfilled", "Breached"]],
				],
				pluck="name",
			)
			for name in active_contracts2:
				refs.append(("Instrument Placement Contract", name))

		if not refs:
			return

		msg_parts = [
			frappe._(
				"Cannot change Reagent Role from '{0}' to '{1}' because this item is "
				"referenced by the following active documents:"
			).format(
				frappe.bold(self.get_doc_before_save().reagent_role),
				frappe.bold(self.reagent_role),
			)
		]
		for dt, dn in refs:
			msg_parts.append(f"<li>{dt}: {dn}</li>")

		frappe.throw(
			"<ol>" + "".join(msg_parts) + "</ol>",
			title=frappe._("Reagent Role Change Blocked"),
		)
