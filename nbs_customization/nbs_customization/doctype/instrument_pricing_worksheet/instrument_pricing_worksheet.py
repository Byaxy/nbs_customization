# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from math import ceil

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt

from nbs_customization.utils.placement import pricing_engine
from nbs_customization.utils.placement.analyzer_menu import (
	get_analyzer_profile,
	resolve_consumable_requirements,
	resolve_cost_basis,
	resolve_test,
)
from nbs_customization.utils.placement.dates import validate_not_future
from nbs_customization.utils.placement.pricing_terms import (
	monthly_test_count,
	test_revenue,
)
from nbs_customization.utils.placement.settings import get_placement_settings
from nbs_customization.utils.pricing import get_current_selling_price


class InstrumentPricingWorksheet(Document):
	def validate(self):
		self._set_default_company()
		validate_not_future(self.posting_date, _("Posting Date"))
		if not flt(self.term_months):
			frappe.throw(_("Contract Term (Months) is required for new worksheets."))
		if self.docstatus == 0:
			self._validate_reagent_items()
			self._validate_annual_interest()
			self._run_calculation()
		self._sync_status()

	def before_submit(self):
		if self.term_months and self.benchmark_status == "Below Tolerance":
			frappe.throw(_("Contract charged value is below the outright benchmark tolerance."))

	def on_submit(self):
		self.approved_by = frappe.session.user
		self.approval_date = frappe.utils.today()
		self._sync_status()

	def on_cancel(self):
		if self.linked_contract:
			frappe.throw(
				frappe._(
					"Cannot cancel a worksheet that has been applied to Contract {0}. Cancel that contract first."
				).format(self.linked_contract)
			)
		self._sync_status()

	def validate_update_after_submit(self):
		self._sync_status()
		super().validate_update_after_submit()

	def _set_default_company(self):
		if not self.company:
			self.company = frappe.db.get_single_value("Global Defaults", "default_company")
		if not self.company:
			frappe.throw(frappe._("Company is required. Set a default Company first."))

	def _validate_reagent_items(self):
		if not self.analyzer_pid:
			return
		if not get_analyzer_profile(self.analyzer_pid):
			frappe.throw(_("Analyzer {0} has no Analyzer Profile.").format(frappe.bold(self.analyzer_pid)))
		seen_reagents = set()
		for row in self.reagent_lines:
			if not flt(row.gross_tests_per_pack or row.tests_per_pack):
				frappe.throw(
					_("Row {0}: Gross Tests per Pack is required and must be positive.").format(row.idx)
				)
			if self.calculation_output_type == "Revenue Share Percentage" and flt(row.price_per_test) <= 0:
				frappe.throw(
					_("Row {0}: Price per Test is required for Revenue Share Percentage.").format(row.idx)
				)
			test = resolve_test(self.analyzer_pid, row.test_parameter)
			if not test:
				frappe.throw(
					_("Row {0}: test {1} is not on this analyzer profile.").format(
						row.idx, frappe.bold(row.test_parameter)
					)
				)
			components = {}
			for component in test.get("reagents", []):
				components.setdefault(component["reagent_item"], set()).add(component["component_role"])
			if row.item_code not in components:
				frappe.throw(
					_("Row {0}: item {1} is not a reagent of test {2}.").format(
						row.idx, frappe.bold(row.item_code), frappe.bold(row.test_parameter)
					)
				)
			if row.component_role and row.component_role not in components[row.item_code]:
				frappe.throw(
					_("Row {0}: component role {1} does not match test {2}.").format(
						row.idx, frappe.bold(row.component_role), frappe.bold(row.test_parameter)
					)
				)
			key = (row.item_code, row.test_parameter, row.component_role or "")
			if key in seen_reagents:
				frappe.throw(_("Row {0}: duplicate reagent component.").format(row.idx))
			seen_reagents.add(key)

		self._validate_component_terms()

		allowed_consumables = {row["item"] for row in resolve_consumable_requirements(self.analyzer_pid)}
		allowed_calibration = _calibration_items(self.analyzer_pid)
		allowed_maintenance = _maintenance_items(self.analyzer_pid)
		seen_consumables = set()
		for row in self.consumable_lines:
			source_type = row.source_type or "Analyzer Consumable"
			if source_type == "Analyzer Consumable":
				if not row.consumption_frequency:
					frappe.throw(_("Row {0}: Consumption Frequency is required.").format(row.idx))
				allowed = allowed_consumables
			elif source_type == "Calibration Material":
				allowed = allowed_calibration
			else:
				allowed = allowed_maintenance
			key = (row.item_code, source_type, row.source_reference or "")
			if key in seen_consumables:
				frappe.throw(
					_("Row {0}: duplicate {1} line for {2}.").format(
						row.idx, frappe.bold(source_type), frappe.bold(row.item_code)
					)
				)
			seen_consumables.add(key)
			if row.item_code not in allowed:
				frappe.throw(
					_("Row {0}: item {1} is not an analyzer {2} requirement.").format(
						row.idx, frappe.bold(row.item_code), frappe.bold(source_type)
					)
				)
			if source_type != "Analyzer Consumable" and not flt(row.quantity_over_term):
				frappe.throw(
					_("Row {0}: cost-basis quantity over term is missing. Reload the cost basis.").format(
						row.idx
					)
				)

	def _validate_component_terms(self):
		by_test = {}
		for row in self.reagent_lines:
			by_test.setdefault(row.test_parameter, []).append(row)
		for test_parameter, rows in by_test.items():
			volumes = {flt(row.monthly_test_volume) for row in rows}
			prices = {flt(row.price_per_test) for row in rows}
			if len(volumes) > 1:
				frappe.throw(
					_("All reagent components for test {0} must use the same Monthly Test Volume.").format(
						frappe.bold(test_parameter)
					)
				)
			if len(prices) > 1:
				frappe.throw(
					_("All reagent components for test {0} must use the same Price per Test.").format(
						frappe.bold(test_parameter)
					)
				)

	def _validate_annual_interest(self):
		if self.contract_type != "RLO":
			self.annual_interest_rate = 0
			return
		if flt(self.annual_interest_rate) <= 0:
			frappe.throw(frappe._("Annual Interest Rate is required for RLO contracts."))

	def _run_calculation(self):
		_refresh_auto_cost_basis(self)
		_resolve_standard_selling_prices(self)
		_compute_lines(self)
		_compute_rollups(self)
		_compute_markup(self)
		self.calculated_by = frappe.session.user
		self.calculated_date = frappe.utils.today()
		self.price_snapshot_date = self.posting_date or frappe.utils.today()

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
		from nbs_customization.utils.placement.assets import capitalize_serial_for_placement

		if not self.analyzer_pid:
			frappe.throw(frappe._("An Analyzer PID must be set before capitalizing."))
		return capitalize_serial_for_placement(
			customer=self.customer,
			customer_name=frappe.db.get_value("Customer", self.customer, "customer_name"),
			analyzer_pid=self.analyzer_pid,
			warehouse=warehouse,
			serial_no=serial_no,
			company=self.company,
		)


def apply_worksheet_pricing(target, source):
	for field in (
		"term_months",
		"analyzer_standard_selling_price",
		"annual_service_maintenance_rate_pct",
		"total_maintenance_cost",
		"standard_sale_base",
		"total_test_reagent_value",
		"total_consumable_value",
		"net_revenue_target",
		"wht_rate_pct",
		"wht_amount",
		"wht_category",
		"wht_rate_date",
		"price_snapshot_date",
		"total_outright_sale_value",
		"outright_gap_amount",
		"outright_gap_pct",
		"benchmark_tolerance_pct",
		"benchmark_status",
		"product_only_standard_sale_base",
		"product_only_outright_value",
		"product_only_contract_value",
		"product_only_gap_pct",
	):
		target.set(field, source.get(field))
	target.term_months = source.term_months or 12
	target.total_recovery_target = source.final_revenue_target
	target.contract_gross_test_revenue = source.total_gross_test_revenue_over_term
	target.contract_charged_value = source.contract_charged_value
	target.min_monthly_value = _worksheet_min_monthly(source)
	target.revenue_share_pct = source.required_revenue_share_pct if source.contract_type == "CPT" else 0


@frappe.whitelist()
def make_instrument_placement_contract(source_name: str, target_doc=None):
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
		target.naming_series = "NBSIPC-.YYYY./.####"
		target.company = source.company or frappe.db.get_single_value("Global Defaults", "default_company")
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
		target.posting_date = source.posting_date or frappe.utils.today()
		target.start_date = source.posting_date or frappe.utils.today()
		target.term_months = source.term_months or 12
		target.end_date = frappe.utils.add_months(target.start_date, target.term_months)
		apply_worksheet_pricing(target, source)
		target.breach_threshold = 3
		target.grace_period_days = 30

	def update_reagent_row(source_row, target_row, source_parent):
		target_row.uom = frappe.db.get_value("Item", source_row.item_code, "stock_uom")
		target_row.cogs_per_unit = source_row.cogs_per_pack
		tests_per_pack = source_row.gross_tests_per_pack or source_row.tests_per_pack
		target_row.min_monthly_qty = (
			ceil(flt(source_row.monthly_test_volume) / flt(tests_per_pack)) if flt(tests_per_pack) else 0
		)

	def update_consumable_row(source_row, target_row, source_parent):
		target_row.uom = frappe.db.get_value("Item", source_row.item_code, "stock_uom")
		target_row.contract_price = 0
		target_row.source_type = source_row.source_type or "Analyzer Consumable"
		target_row.source_reference = source_row.source_reference or ""

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
					"component_role": "component_role",
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
		if flt(line.selling_price_per_pack) and flt(line.gross_tests_per_pack or line.tests_per_pack):
			total += ceil(
				flt(line.monthly_test_volume) / flt(line.gross_tests_per_pack or line.tests_per_pack)
			) * flt(line.selling_price_per_pack)
	return total


def _refresh_auto_cost_basis(ws):
	"""Recalculate auto-loaded cost-basis rows for the current term."""
	if not ws.analyzer_pid or not ws.term_months:
		return
	if not get_analyzer_profile(ws.analyzer_pid):
		return
	rows = resolve_cost_basis(
		ws.analyzer_pid,
		ws.term_months,
		ws.operational_days_per_month,
		on_date=ws.posting_date,
		monthly_test_volume=monthly_test_count(ws.reagent_lines),
	)
	by_key = {(row["source_type"], row["source_reference"] or "", row["item_code"]): row for row in rows}
	for line in list(ws.consumable_lines):
		if not line.is_auto:
			continue
		key = (line.source_type, line.source_reference or "", line.item_code)
		row = by_key.get(key)
		if not row:
			ws.remove(line)
			continue
		line.quantity_over_term = row["quantity_over_term"]
		line.cogs_per_unit = row["cogs_per_unit"]
		line.standard_selling_price_per_unit = row["standard_selling_price_per_unit"]
		line.consumption_frequency = "Computed Over Term"


def _calibration_items(analyzer_item):
	profile = get_analyzer_profile(analyzer_item)
	if not profile:
		return set()
	return {row.item for row in profile.consumables if row.role in ("Calibrator", "Control")}


def _maintenance_items(analyzer_item):
	profile = get_analyzer_profile(analyzer_item)
	return {row.item for row in profile.maintenance} if profile else set()


def _resolve_standard_selling_prices(ws):
	if not flt(ws.analyzer_standard_selling_price):
		ws.analyzer_standard_selling_price = get_current_selling_price(ws.analyzer_pid, ws.posting_date)
	if flt(ws.analyzer_standard_selling_price) <= 0:
		frappe.throw(
			frappe._("Analyzer {0} needs a Standard Selling Item Price before pricing.").format(
				frappe.bold(ws.analyzer_pid)
			)
		)
	if not flt(ws.annual_service_maintenance_rate_pct):
		ws.annual_service_maintenance_rate_pct = get_placement_settings()["annual_service_rate_pct"]
	for line in ws.reagent_lines:
		if not flt(line.standard_selling_price_per_pack):
			line.standard_selling_price_per_pack = get_current_selling_price(line.item_code, ws.posting_date)
		if flt(line.standard_selling_price_per_pack) <= 0:
			frappe.throw(
				frappe._("Reagent {0} needs a Standard Selling Item Price before pricing.").format(
					frappe.bold(line.item_code)
				)
			)
	for line in ws.consumable_lines:
		if not flt(line.standard_selling_price_per_unit):
			line.standard_selling_price_per_unit = get_current_selling_price(line.item_code, ws.posting_date)


def _term_months(ws):
	months = flt(ws.term_months)
	if months <= 0:
		frappe.throw(frappe._("Contract Term (Months) must be positive."))
	return months


def _compute_lines(ws):
	term_months = _term_months(ws)
	seen_revenue_tests = set()
	for line in ws.reagent_lines:
		line.gross_tests_per_pack = flt(line.gross_tests_per_pack or line.tests_per_pack)
		if line.gross_tests_per_pack <= 0:
			frappe.throw(frappe._("Line {0}: Gross Tests per Pack must be positive.").format(line.idx))
		line.reportable_tests_per_pack = line.gross_tests_per_pack
		line.total_tests_over_term = flt(line.monthly_test_volume) * term_months
		line.packs_needed = pricing_engine.declared_packs(
			line.monthly_test_volume, term_months, line.reportable_tests_per_pack
		)
		line.total_reagent_value_line = flt(line.packs_needed) * flt(line.standard_selling_price_per_pack)
		line.total_cost_line = flt(line.packs_needed) * flt(line.cogs_per_pack)
		bg_month = flt(line.bg_consumption_ml_month)
		if not bg_month:
			bg_month = flt(line.bg_consumption_ml_day) * flt(ws.operational_days_per_month)
		line.total_consumption_ml_month = bg_month + flt(line.consumption_ml_per_test) * flt(
			line.monthly_test_volume
		)
		if (
			ws.calculation_output_type == "Revenue Share Percentage"
			and flt(line.price_per_test)
			and line.test_parameter not in seen_revenue_tests
		):
			line.total_gross_revenue_line = flt(line.total_tests_over_term) * flt(line.price_per_test)
			seen_revenue_tests.add(line.test_parameter)
		else:
			line.total_gross_revenue_line = 0

	term_years = term_months / 12
	for line in ws.consumable_lines:
		if flt(line.quantity_over_term):
			line.total_units_over_term = flt(line.quantity_over_term)
		else:
			qty = flt(line.consumption_qty)
			freq = line.consumption_frequency
			if freq == "Per Month":
				line.total_units_over_term = qty * term_months
			elif freq == "Per Service Interval":
				line.total_units_over_term = qty * flt(line.services_per_year) * term_years
			elif freq == "Per Year":
				line.total_units_over_term = qty * term_years
			else:
				line.total_units_over_term = 0
		if flt(line.total_units_over_term) > 0 and flt(line.standard_selling_price_per_unit) <= 0:
			frappe.throw(
				_("Consumable {0} needs a Standard Selling Item Price before pricing.").format(
					frappe.bold(line.item_code)
				)
			)
		line.total_value_line = flt(line.total_units_over_term) * flt(line.standard_selling_price_per_unit)
		line.total_cost_line = flt(line.total_units_over_term) * flt(line.cogs_per_unit)


def _compute_rollups(ws):
	ws.total_test_reagent_value = flt(sum(flt(line.total_reagent_value_line) for line in ws.reagent_lines), 2)
	ws.total_consumable_value = flt(sum(flt(line.total_value_line) for line in ws.consumable_lines), 2)
	ws.total_test_reagent_cogs = flt(sum(flt(line.total_cost_line) for line in ws.reagent_lines), 2)
	ws.total_consumable_cost = flt(sum(flt(line.total_cost_line) for line in ws.consumable_lines), 2)
	ws.total_monthly_tests = flt(monthly_test_count(ws.reagent_lines), 2)
	ws.total_tests_over_term = flt(ws.total_monthly_tests * _term_months(ws), 2)
	ws.total_reagent_packs = sum(int(line.packs_needed or 0) for line in ws.reagent_lines)
	ws.total_consumable_units = flt(sum(flt(line.total_units_over_term) for line in ws.consumable_lines), 2)
	ws.total_cogs = flt(ws.total_test_reagent_cogs + ws.total_consumable_cost, 2)
	term_months = _term_months(ws)
	service_base = flt(ws.analyzer_standard_selling_price)
	maintenance, interest = pricing_engine.capital_costs(
		service_base,
		ws.annual_service_maintenance_rate_pct,
		ws.annual_interest_rate,
		term_months,
		ws.contract_type == "RLO",
	)
	ws.wht_rate_pct = _wht_rate(ws)
	try:
		targets = pricing_engine.target_amounts(
			service_base,
			ws.total_test_reagent_value,
			ws.total_consumable_value,
			maintenance,
			interest,
			ws.profit_margin_pct,
			ws.wht_rate_pct,
		)
	except ValueError as exc:
		frappe.throw(str(exc))
	ws.total_maintenance_cost = maintenance
	ws.total_interest_cost = interest
	ws.standard_sale_base = targets["standard_sale_base"]
	ws.total_cost_base = targets["total_cost_base"]
	ws.profit_amount = targets["profit_amount"]
	ws.net_revenue_target = targets["net_revenue_target"]
	ws.wht_amount = targets["wht_amount"]
	ws.final_revenue_target = targets["final_revenue_target"]
	ws.fixed_cost_to_recover = targets["fixed_cost_to_recover"]
	ws.contract_charged_value = ws.final_revenue_target
	ws.total_outright_sale_value = ws.standard_sale_base
	ws.outright_gap_amount = flt(ws.net_revenue_target - ws.total_outright_sale_value, 2)
	ws.outright_gap_pct = flt(
		flt(ws.outright_gap_amount) / flt(ws.total_outright_sale_value) * 100
		if flt(ws.total_outright_sale_value)
		else 0,
		2,
	)
	ws.benchmark_tolerance_pct = (
		flt(ws.benchmark_tolerance_pct) or get_placement_settings()["outright_floor_pct"]
	)
	ws.benchmark_status = _benchmark_status(ws.outright_gap_pct, ws.benchmark_tolerance_pct)
	ws.product_only_standard_sale_base = (
		service_base + flt(ws.total_test_reagent_value) + flt(ws.total_consumable_value)
	)
	ws.product_only_outright_value = ws.product_only_standard_sale_base
	ws.product_only_contract_value = flt(ws.net_revenue_target) - flt(ws.total_maintenance_cost)
	ws.product_only_gap_pct = (
		(flt(ws.product_only_contract_value) - flt(ws.product_only_outright_value))
		/ flt(ws.product_only_outright_value)
		* 100
		if flt(ws.product_only_outright_value)
		else 0
	)


def _wht_rate(ws):
	category = (
		frappe.db.get_value("Customer", ws.customer, "tax_withholding_category") if ws.customer else None
	)
	ws.wht_category = category
	rate_date = ws.posting_date or ws.wht_rate_date or frappe.utils.today()
	ws.wht_rate_date = rate_date
	if not category:
		return 0
	doc = frappe.get_cached_doc("Tax Withholding Category", category)
	try:
		row = doc.get_applicable_tax_row(frappe.utils.getdate(rate_date), None)
		return abs(flt(row.tax_withholding_rate))
	except frappe.ValidationError:
		return 0


def _benchmark_status(gap_pct, tolerance):
	tol = flt(tolerance) or 5
	if gap_pct < -tol:
		return "Below Tolerance"
	if gap_pct < 0:
		return "Within Tolerance"
	return "At or Above Outright"


def _compute_markup(ws):
	if ws.calculation_output_type == "Markup Factor on Reagent Price":
		if flt(ws.total_test_reagent_value) <= 0:
			frappe.throw(_("Total Test Reagent Standard Selling value is zero."))
		ws.markup_factor = flt(ws.final_revenue_target) / flt(ws.total_test_reagent_value)
		for line in ws.reagent_lines:
			line.markup_factor_applied = ws.markup_factor
			line.selling_price_per_pack = flt(line.standard_selling_price_per_pack) * flt(ws.markup_factor)
			line.selling_price_per_test = (
				flt(line.selling_price_per_pack) / flt(line.reportable_tests_per_pack)
				if flt(line.reportable_tests_per_pack)
				else 0
			)
	else:
		total_gross = test_revenue(ws.reagent_lines, _term_months(ws), "price_per_test")
		ws.total_gross_test_revenue_over_term = total_gross
		ws.required_revenue_share_pct = flt(ws.final_revenue_target) / total_gross * 100 if total_gross else 0
		ws.required_revenue_share_amount = flt(ws.final_revenue_target, 2)
		ws.contract_charged_value = ws.final_revenue_target
