# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from math import ceil
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
		item_codes = []
		for row in self.reagent_lines:
			if row.item_code:
				item_codes.append(row.item_code)
		for row in self.consumable_lines:
			if row.item_code:
				item_codes.append(row.item_code)
		validate_items_belong_to_analyzer(self.analyzer_pid, item_codes, throw=True)

	def _validate_annual_interest(self):
		if self.contract_type == "RLO":
			if self.annual_interest_rate is None or self.annual_interest_rate <= 0:
				frappe.throw(frappe._("Annual Interest Rate is required for RLO contracts."))
		else:
			self.annual_interest_rate = 0

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
	def apply_worksheet_to_contract(self, asset, customer_site):
		if self.docstatus != 1:
			frappe.throw(frappe._("Worksheet must be submitted before applying to a Contract."))
		if self.linked_contract:
			frappe.throw(frappe._("Worksheet already applied to Contract {0}.").format(self.linked_contract))

		start = frappe.utils.today()
		end = frappe.utils.add_years(start, self.contract_years or 1)

		monthly_volumes = [ln.monthly_test_volume or 0 for ln in self.reagent_lines]
		declared_vol = max(monthly_volumes) if monthly_volumes else 0

		min_monthly_val = 0
		for line in self.reagent_lines:
			if line.selling_price_per_pack:
				min_qty = ceil((line.monthly_test_volume or 0) / (line.tests_per_pack or 1))
				min_monthly_val += min_qty * line.selling_price_per_pack

		serial_no = frappe.db.get_value("Asset", asset, "custom_serial_no")
		analyzer_desc = frappe.db.get_value("Item", self.analyzer_pid, "description") or ""
		customer_name = frappe.db.get_value("Customer", self.customer, "customer_name") or ""

		contract = frappe.get_doc(
			{
				"doctype": "Instrument Placement Contract",
				"naming_series": "NBSIPC-.YYYY./.####",
				"contract_title": f"{customer_name} - {self.contract_type} Placement Contract",
				"contract_type": self.contract_type,
				"customer": self.customer,
				"customer_site": customer_site,
				"asset": asset,
				"serial_no": serial_no or "",
				"analyzer_pid": self.analyzer_pid,
				"analyzer_description": analyzer_desc,
				"start_date": start,
				"end_date": end,
				"pricing_worksheet": self.name,
				"total_recovery_target": self.final_revenue_target,
				"min_monthly_value": min_monthly_val,
				"breach_threshold": 3,
				"grace_period_days": 30,
				"revenue_share_pct": self.required_revenue_share_pct if self.contract_type == "CPT" else 0,
			}
		)

		for line in self.reagent_lines:
			uom = frappe.db.get_value("Item", line.item_code, "stock_uom")
			min_qty = ceil(line.monthly_test_volume / line.tests_per_pack) if line.tests_per_pack else 0
			contract.append(
				"contract_reagent_lines",
				{
					"test_parameter": line.test_parameter,
					"item_code": line.item_code,
					"uom": uom,
					"standard_price": line.cogs_per_pack,
					"contract_price": line.selling_price_per_pack or 0,
					"qty_required_total": line.packs_needed or 0,
					"min_monthly_qty": min_qty,
					"cogs_per_unit": line.cogs_per_pack,
					"monthly_test_volume": line.monthly_test_volume,
					"agreed_test_price": line.price_per_test or 0,
				},
			)

		for line in self.consumable_lines:
			uom = frappe.db.get_value("Item", line.item_code, "stock_uom")
			contract.append(
				"contract_consumable_lines",
				{
					"item_code": line.item_code,
					"uom": uom,
					"standard_price": line.cogs_per_unit,
					"contract_price": 0,
					"qty_required_total": line.total_units_over_term or 0,
					"cogs_per_unit": line.cogs_per_unit,
				},
			)

		contract.insert(ignore_permissions=True)

		price_list = _create_contract_price_list(contract, self)
		contract.contract_price_list = price_list.name
		contract.save(ignore_permissions=True)

		self.linked_contract = contract.name
		self.save(ignore_permissions=True)

		return contract.name


def _compute_lines(ws):
	for line in ws.reagent_lines:
		line.total_tests_over_term = (line.monthly_test_volume or 0) * 12 * (ws.contract_years or 1)
		if line.tests_per_pack:
			line.packs_needed = ceil(line.total_tests_over_term / line.tests_per_pack)
		else:
			line.packs_needed = 0
			frappe.msgprint(
				frappe._("Line {0}: tests_per_pack is zero. Set packs_needed to 0.").format(line.idx),
				alert=True,
				indicator="orange",
			)
		line.total_cost_line = (line.packs_needed or 0) * (line.cogs_per_pack or 0)

		if ws.calculation_output_type == "Revenue Share Percentage" and line.price_per_test:
			line.total_gross_revenue_line = line.total_tests_over_term * line.price_per_test
		else:
			line.total_gross_revenue_line = 0

	for line in ws.consumable_lines:
		years = ws.contract_years
		freq = line.consumption_frequency
		qty = line.consumption_qty or 0

		if freq == "Per Month":
			line.total_units_over_term = qty * 12 * years
		elif freq == "Per Service Interval":
			line.total_units_over_term = 0
			frappe.msgprint(
				frappe._(
					"Line {0}: Consumption frequency is 'Per Service Interval' but no "
					"service event count is available to compute total consumption. "
					"Set total_units_over_term manually or change the frequency."
				).format(line.idx),
				alert=True,
				indicator="orange",
			)
		elif freq == "Per Year":
			line.total_units_over_term = qty * years
		else:
			line.total_units_over_term = 0

		line.total_cost_line = line.total_units_over_term * (line.cogs_per_unit or 0)


def _compute_rollups(ws):
	total_reagent_cogs = 0
	total_consumable_cost = 0

	for line in ws.reagent_lines:
		total_reagent_cogs += line.total_cost_line or 0
	for line in ws.consumable_lines:
		total_consumable_cost += line.total_cost_line or 0

	ws.total_test_reagent_cogs = total_reagent_cogs
	ws.total_consumable_cost = total_consumable_cost

	interest_factor = 1 + (ws.annual_interest_rate or 0) / 100 * ws.contract_years
	landed = ws.analyzer_landed_cost or 0

	if ws.annual_maintenance_cost_rate and ws.analyzer_landed_cost:
		ws.total_maintenance_cost = (
			(ws.annual_maintenance_cost_rate / 100) * ws.analyzer_landed_cost * ws.contract_years
		)

	ws.fixed_cost_to_recover = (
		landed * interest_factor + (ws.total_maintenance_cost or 0) + total_consumable_cost
	)

	ws.total_cost_base = ws.fixed_cost_to_recover + total_reagent_cogs
	ws.profit_amount = (ws.profit_margin_pct or 0) / 100 * ws.total_cost_base
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
			line.selling_price_per_pack = (line.cogs_per_pack or 0) * ws.markup_factor
			if line.tests_per_pack:
				line.selling_price_per_test = line.selling_price_per_pack / line.tests_per_pack
			else:
				line.selling_price_per_test = 0

	elif ws.calculation_output_type == "Revenue Share Percentage":
		total_gross = sum((line.total_gross_revenue_line or 0) for line in ws.reagent_lines)
		ws.total_gross_test_revenue_over_term = total_gross
		if total_gross:
			ws.required_revenue_share_pct = (ws.final_revenue_target / total_gross) * 100
		else:
			ws.required_revenue_share_pct = 0


def _create_contract_price_list(contract, ws):
	pl = frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": f"Contract Pricing - {contract.name}",
			"currency": frappe.db.get_single_value("Global Defaults", "default_currency"),
			"selling": 1,
			"enabled": 1,
			"buying": 0,
		}
	).insert(ignore_permissions=True)

	for line in ws.reagent_lines:
		if (line.selling_price_per_pack or 0) > 0:
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"price_list": pl.name,
					"item_code": line.item_code,
					"price_list_rate": line.selling_price_per_pack,
					"uom": frappe.db.get_value("Item", line.item_code, "stock_uom"),
					"selling": 1,
					"valid_from": frappe.utils.today(),
				}
			).insert(ignore_permissions=True)

	return pl
