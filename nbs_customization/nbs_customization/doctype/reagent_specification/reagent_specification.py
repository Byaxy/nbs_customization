# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReagentSpecification(Document):
	def validate(self):
		if not self.is_new() and self.has_value_changed("item"):
			frappe.throw(frappe._("Item cannot be changed after the Reagent Specification is created."))
		self._validate_item_is_not_analyzer()
		self._set_item_defaults()
		if self.is_new() or not self.has_value_changed("reagent_role"):
			return
		self._validate_no_active_downstream_references()

	def on_update(self):
		_set_item_specification(self.item, self.name)

	def on_trash(self):
		_clear_item_specification(self.item, self.name)

	def _validate_item_is_not_analyzer(self):
		if not self.item:
			return
		is_analyzer = frappe.db.get_value("Item", self.item, "custom_analyzer_profile") or frappe.db.exists(
			"Analyzer Profile", {"analyzer_item": self.item}
		)
		if is_analyzer:
			frappe.throw(
				frappe._("Item {0} is an analyzer and cannot have a Reagent Specification.").format(
					frappe.bold(self.item)
				)
			)

	def _set_item_defaults(self):
		if not self.item:
			return
		item = frappe.db.get_value(
			"Item", self.item, ["stock_uom", "valuation_rate", "last_purchase_rate"], as_dict=True
		)
		if not item:
			return
		self.pack_uom = item.stock_uom
		if not (self.is_new() or self.has_value_changed("item")):
			return
		if self.default_cogs_per_pack or self.default_cogs_per_unit:
			return
		cost = item.valuation_rate or item.last_purchase_rate or 0
		if self.reagent_role == "Test Reagent":
			self.default_cogs_per_pack = cost
			self.default_cogs_per_unit = 0
		elif self.reagent_role == "Non-Test Consumable":
			self.default_cogs_per_unit = cost
			self.default_cogs_per_pack = 0

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


def _set_item_specification(item, specification):
	if item and specification:
		frappe.db.set_value("Item", item, "custom_reagent_specification", specification)


def _clear_item_specification(item, specification):
	if not item or not specification:
		return
	if frappe.db.get_value("Item", item, "custom_reagent_specification") == specification:
		frappe.db.set_value("Item", item, "custom_reagent_specification", None)
