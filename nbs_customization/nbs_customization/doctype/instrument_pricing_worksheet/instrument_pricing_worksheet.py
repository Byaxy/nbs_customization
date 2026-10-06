# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from math import ceil

import frappe
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt

from nbs_customization.utils.placement.valid_items import validate_items_belong_to_analyzer


class InstrumentPricingWorksheet(Document):
	def validate(self):
		if self.docstatus == 0:
			self._validate_reagent_items()
			self._validate_annual_interest()
			self._run_calculation()
		self._sync_status()

	def on_submit(self):
		self.approved_by = frappe.session.user
		self.approval_date = frappe.utils.today()
		self._sync_status()

	def on_cancel(self):
		if self.linked_contract:
			frappe.throw(
				frappe._(
					"Cannot cancel a worksheet that has been applied to "
					"Contract {0}. Cancel that contract first."
				).format(self.linked_contract)
			)
		self._sync_status()

	def validate_update_after_submit(self):
		self._sync_status()
		super().validate_update_after_submit()

	def _validate_reagent_items(self):
		if not self.analyzer_pid:
			return
		spec = frappe.db.get_value("Instrument Specification", {"item": self.analyzer_pid}, "name")
		spec_params = set()
		param_reagent_map = {}
		if spec:
			for m in frappe.db.get_all(
				"Instrument Test Method",
				filters={"parent": spec},
				fields=["test_parameter", "required_reagent"],
			):
				if m.get("test_parameter"):
					spec_params.add(m["test_parameter"])
					param_reagent_map[m["test_parameter"]] = m.get("required_reagent")
		spec_consumables = set()
		if spec:
			spec_consumables = set(
				frappe.db.get_all(
					"Instrument Consumable Requirement",
					filters={"parent": spec},
					pluck="consumable_item",
				)
			)
		item_codes = []
		for row in self.reagent_lines:
			if row.test_parameter and row.test_parameter not in spec_params:
				frappe.throw(
					frappe._("Test Parameter {0} is not on this analyzer's specification.").format(
						frappe.bold(row.test_parameter)
					)
				)
			if row.test_parameter and row.item_code:
				mapped = param_reagent_map.get(row.test_parameter)
				if mapped and row.item_code != mapped:
					frappe.throw(
						frappe._(
							"Item {0} is not mapped to Test Parameter {1} on this analyzer's specification."
						).format(frappe.bold(row.item_code), frappe.bold(row.test_parameter))
					)
			if row.item_code:
				item_codes.append(row.item_code)
		for row in self.consumable_lines:
			if not row.consumption_frequency:
				frappe.throw(frappe._("Row {0}: Consumption Frequency is required.").format(row.idx))
			if row.item_code and row.item_code not in spec_consumables:
				frappe.throw(
					frappe._("Item {0} is not on this analyzer's Required Consumables.").format(
						frappe.bold(row.item_code)
					)
				)
			if row.item_code:
				item_codes.append(row.item_code)
		validate_items_belong_to_analyzer(self.analyzer_pid, item_codes, throw=True)

	def _validate_annual_interest(self):
		if self.contract_type != "RLO":
			# Interest applies to RLO only; clear stale values so stored data matches calculation.
			self.annual_interest_rate = 0
			return
		if flt(self.annual_interest_rate) <= 0:
			frappe.throw(frappe._("Annual Interest Rate is required for RLO contracts."))

	def _run_calculation(self):
		_compute_lines(self)
		_compute_rollups(self)
		_compute_markup_or_revenue_share(self)
		self.calculated_by = frappe.session.user
		self.calculated_date = frappe.utils.today()

	def _sync_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 2:
			self.status = "Cancelled"
		elif self.linked_contract:
			self.status = "Applied to Contract"
		else:
			self.status = "Approved"

	@frappe.whitelist()
	def capitalize_analyzer(self, warehouse: str, serial_no: str):
		"""Create an unlinked placement Asset for this worksheet's analyzer."""
		from nbs_customization.utils.placement.assets import capitalize_serial_for_placement

		if not self.analyzer_pid:
			frappe.throw(frappe._("An Analyzer PID must be set before capitalizing."))
		return capitalize_serial_for_placement(
			customer=self.customer,
			customer_name=frappe.db.get_value("Customer", self.customer, "customer_name"),
			analyzer_pid=self.analyzer_pid,
			warehouse=warehouse,
			serial_no=serial_no,
		)


@frappe.whitelist()
def make_instrument_placement_contract(source_name: str, target_doc=None):
	"""Map a submitted worksheet to an unsaved Instrument Placement Contract."""
	ws = frappe.get_doc("Instrument Pricing Worksheet", source_name)
	if ws.docstatus != 1:
		frappe.throw(frappe._("Worksheet must be submitted before applying to a Contract."))
	if ws.linked_contract:
		frappe.throw(frappe._("Worksheet already applied to Contract {0}.").format(ws.linked_contract))

	args = frappe.flags.args or {}
	if isinstance(args, str):
		args = frappe.parse_json(args)
	asset = args.get("asset") or ""
	customer_site = args.get("customer_site")

	def set_missing_values(source, target):
		target.pricing_worksheet = source.name
		target.contract_title = "{0} - {1} Placement Contract".format(
			source.customer_name or source.customer, source.contract_type
		)
		target.contract_type = source.contract_type
		target.customer = source.customer
		target.customer_site = customer_site
		target.asset = asset
		if asset:
			target.serial_no = frappe.db.get_value("Asset", asset, "custom_serial_no") or ""
		else:
			target.serial_no = ""
		target.analyzer_pid = source.analyzer_pid
		target.analyzer_description = frappe.db.get_value("Item", source.analyzer_pid, "description") or ""
		target.start_date = frappe.utils.today()
		target.end_date = frappe.utils.add_years(target.start_date, source.contract_years or 1)
		target.total_recovery_target = source.final_revenue_target
		target.min_monthly_value = _worksheet_min_monthly(source)
		target.breach_threshold = 3
		target.grace_period_days = 30
		target.revenue_share_pct = source.required_revenue_share_pct if source.contract_type == "CPT" else 0

	def update_reagent_row(source_row, target_row, source_parent):
		target_row.uom = frappe.db.get_value("Item", source_row.item_code, "stock_uom")
		# Contract amendments gate the pack-size lookup on this field; without
		# it the divisor falls back to 1 and monthly charges inflate.
		target_row.cogs_per_unit = source_row.cogs_per_pack
		target_row.min_monthly_qty = (
			ceil(flt(source_row.monthly_test_volume) / flt(source_row.tests_per_pack))
			if flt(source_row.tests_per_pack)
			else 0
		)

	def update_consumable_row(source_row, target_row, source_parent):
		target_row.uom = frappe.db.get_value("Item", source_row.item_code, "stock_uom")
		target_row.contract_price = 0

	return get_mapped_doc(
		"Instrument Pricing Worksheet",
		source_name,
		{
			"Instrument Pricing Worksheet": {
				"doctype": "Instrument Placement Contract",
				"validation": {"docstatus": ["=", 1]},
			},
			"Worksheet Test Reagent Line": {
				"doctype": "Contract Test Reagent Line",
				"field_map": {
					"cogs_per_pack": "standard_price",
					"selling_price_per_pack": "contract_price",
					"packs_needed": "qty_required_total",
					"price_per_test": "agreed_test_price",
				},
				"postprocess": update_reagent_row,
			},
			"Worksheet Consumable Line": {
				"doctype": "Contract Consumable Line",
				"field_map": {
					"cogs_per_unit": "standard_price",
					"total_units_over_term": "qty_required_total",
				},
				"postprocess": update_consumable_row,
			},
		},
		target_doc,
		set_missing_values,
	)


def _worksheet_min_monthly(source):
	total = 0
	for line in source.reagent_lines:
		if flt(line.selling_price_per_pack) and flt(line.tests_per_pack):
			total += ceil(flt(line.monthly_test_volume) / flt(line.tests_per_pack)) * flt(
				line.selling_price_per_pack
			)
	return total


def _compute_lines(ws):
	years = flt(ws.contract_years) or 1
	for line in ws.reagent_lines:
		line.total_tests_over_term = flt(line.monthly_test_volume) * 12 * years
		if flt(line.tests_per_pack):
			line.packs_needed = ceil(line.total_tests_over_term / flt(line.tests_per_pack))
		else:
			line.packs_needed = 0
			frappe.msgprint(
				frappe._("Line {0}: tests_per_pack is zero. Set packs_needed to 0.").format(line.idx),
				alert=True,
				indicator="orange",
			)
		line.total_cost_line = flt(line.packs_needed) * flt(line.cogs_per_pack)

		if ws.calculation_output_type == "Revenue Share Percentage" and flt(line.price_per_test):
			line.total_gross_revenue_line = flt(line.total_tests_over_term) * flt(line.price_per_test)
		else:
			line.total_gross_revenue_line = 0

	for line in ws.consumable_lines:
		freq = line.consumption_frequency
		qty = flt(line.consumption_qty)

		if freq == "Per Month":
			line.total_units_over_term = qty * 12 * years
		elif freq == "Per Service Interval":
			services = flt(line.services_per_year)
			line.total_units_over_term = qty * services * years
			if not services:
				frappe.msgprint(
					frappe._(
						"Line {0}: Consumption frequency is 'Per Service Interval' but "
						"No. of Services per Year is zero. Set it to include this "
						"consumable in recovery."
					).format(line.idx),
					alert=True,
					indicator="orange",
				)
		elif freq == "Per Year":
			line.total_units_over_term = qty * years
		else:
			line.total_units_over_term = 0

		line.total_cost_line = flt(line.total_units_over_term) * flt(line.cogs_per_unit)


def _compute_rollups(ws):
	total_reagent_cogs = 0
	total_consumable_cost = 0

	for line in ws.reagent_lines:
		total_reagent_cogs += flt(line.total_cost_line)
	for line in ws.consumable_lines:
		total_consumable_cost += flt(line.total_cost_line)

	ws.total_test_reagent_cogs = total_reagent_cogs
	ws.total_consumable_cost = total_consumable_cost

	years = flt(ws.contract_years)
	if ws.contract_type == "RLO":
		interest_factor = 1 + flt(ws.annual_interest_rate) / 100 * years
	else:
		interest_factor = 1
	landed = flt(ws.analyzer_landed_cost)

	if flt(ws.annual_maintenance_cost_rate) and landed:
		ws.total_maintenance_cost = (flt(ws.annual_maintenance_cost_rate) / 100) * landed * years

	ws.fixed_cost_to_recover = (
		landed * interest_factor + flt(ws.total_maintenance_cost) + total_consumable_cost
	)

	ws.total_cost_base = ws.fixed_cost_to_recover + total_reagent_cogs
	ws.profit_amount = flt(ws.profit_margin_pct) / 100 * flt(ws.total_cost_base)
	ws.final_revenue_target = ws.total_cost_base + ws.profit_amount


def _compute_markup_or_revenue_share(ws):
	if ws.calculation_output_type == "Markup Factor on Reagent Price":
		if ws.total_test_reagent_cogs:
			ws.markup_factor = ws.final_revenue_target / ws.total_test_reagent_cogs
		else:
			ws.markup_factor = 0
			frappe.msgprint(
				"Total Test Reagent COGS is zero — markup factor set to 0.",
				alert=True,
				indicator="orange",
			)

		for line in ws.reagent_lines:
			line.markup_factor_applied = ws.markup_factor
			line.selling_price_per_pack = flt(line.cogs_per_pack) * flt(ws.markup_factor)
			if flt(line.tests_per_pack):
				line.selling_price_per_test = flt(line.selling_price_per_pack) / flt(line.tests_per_pack)
			else:
				line.selling_price_per_test = 0

	elif ws.calculation_output_type == "Revenue Share Percentage":
		total_gross = sum((line.total_gross_revenue_line or 0) for line in ws.reagent_lines)
		ws.total_gross_test_revenue_over_term = total_gross
		if total_gross:
			ws.required_revenue_share_pct = (ws.final_revenue_target / total_gross) * 100
		else:
			ws.required_revenue_share_pct = 0
