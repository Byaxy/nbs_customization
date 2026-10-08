# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from math import ceil

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from nbs_customization.utils.placement.recovery import recompute_contract_recovery as _recompute
from nbs_customization.utils.placement.valid_items import validate_items_belong_to_analyzer


class InstrumentPlacementContract(Document):
	def validate(self):
		self._validate_contract_lines()
		self._validate_asset_link()
		self._compute_duration()
		self._compute_min_monthly_value()
		self._compute_cpt_fields()
		self._validate_pricing_worksheet_link()
		self._assert_matches_worksheet()

	def before_submit(self):
		self._require_contract_lines()
		self._require_pricing_worksheet()
		self._require_asset()
		if not self.contract_price_list:
			self.contract_price_list = _create_contract_price_list(self).name

	def on_submit(self):
		self.approved_by = frappe.session.user
		self.approval_date = frappe.utils.today()
		self.db_set("approved_by", self.approved_by)
		self.db_set("approval_date", self.approval_date)
		self._activate_contract()
		self.db_set("outstanding_on_contract", self.total_recovery_target or 0)
		self._link_pricing_worksheet()

	def on_cancel(self):
		self._validate_no_deployment()
		self._clear_asset_link()
		self._unlink_pricing_worksheet()

	def _validate_contract_lines(self):
		if not self.analyzer_pid:
			return
		item_codes = []
		for row in self.contract_reagent_lines:
			if row.item_code:
				item_codes.append(row.item_code)
		for row in self.contract_consumable_lines:
			if row.item_code:
				item_codes.append(row.item_code)
		validate_items_belong_to_analyzer(self.analyzer_pid, item_codes, throw=True)

		for line in self.contract_reagent_lines:
			if line.contract_price and line.standard_price:
				line.price_uplift = line.contract_price - line.standard_price
			else:
				line.price_uplift = 0

		for line in self.contract_consumable_lines:
			if line.contract_price and line.standard_price:
				line.price_uplift = line.contract_price - line.standard_price
			else:
				line.price_uplift = 0

	def _validate_asset_link(self):
		if not self.asset:
			return
		if frappe.db.get_value("Asset", self.asset, "docstatus") == 2:
			frappe.throw(frappe._("Asset {0} is cancelled.").format(frappe.bold(self.asset)))
		linked = frappe.db.get_value("Asset", self.asset, "custom_current_placement_contract")
		if linked and linked != self.name:
			frappe.throw(
				frappe._("Asset {0} is already linked to Contract {1}.").format(
					frappe.bold(self.asset), frappe.bold(linked)
				)
			)
		spec = frappe.db.get_value("Asset", self.asset, "custom_instrument_specification")
		if spec:
			spec_item = frappe.db.get_value("Instrument Specification", spec, "item")
			if spec_item and spec_item != self.analyzer_pid:
				frappe.throw(
					frappe._("Asset {0} is for analyzer {1}, not {2}.").format(
						frappe.bold(self.asset), frappe.bold(spec_item), frappe.bold(self.analyzer_pid)
					)
				)
			return
		serial_no = frappe.db.get_value("Asset", self.asset, "custom_serial_no")
		if serial_no and frappe.db.exists("Serial No", serial_no):
			serial_item = frappe.db.get_value("Serial No", serial_no, "item_code")
			if serial_item and serial_item != self.analyzer_pid:
				frappe.throw(
					frappe._("Asset {0} (Serial {1}) is for analyzer {2}, not {3}.").format(
						frappe.bold(self.asset),
						frappe.bold(serial_no),
						frappe.bold(serial_item),
						frappe.bold(self.analyzer_pid),
					)
				)

	def _compute_duration(self):
		if self.start_date and self.end_date:
			start = frappe.utils.getdate(self.start_date)
			end = frappe.utils.getdate(self.end_date)
			delta = (end.year - start.year) * 12 + (end.month - start.month)
			self.contract_duration_months = max(delta + 1, 0)

	def _compute_min_monthly_value(self):
		total = 0
		for line in self.contract_reagent_lines:
			if line.contract_price and line.min_monthly_qty:
				total += line.contract_price * line.min_monthly_qty
		self.min_monthly_value = total

	def _compute_cpt_fields(self):
		if self.contract_type != "CPT":
			return
		pct = (self.revenue_share_pct or 0) / 100
		total_gross = 0
		for line in self.contract_reagent_lines:
			gross = (line.monthly_test_volume or 0) * (line.agreed_test_price or 0)
			line.fixed_monthly_gross_revenue = gross
			line.fixed_monthly_share_amount = gross * pct
			total_gross += gross
		self.fixed_monthly_gross_revenue = total_gross
		self.fixed_monthly_share_amount = total_gross * pct

	def _assert_matches_worksheet(self):
		"""Block drift: commercial mirrors must equal the linked worksheet.

		The worksheet is the single source of truth. Amendments are the only
		authorized mutation path and save with
		ignore_validate_update_after_submit, which exempts this check.
		"""
		if self.flags.ignore_validate_update_after_submit or not self.pricing_worksheet:
			return
		ws = frappe.get_cached_doc("Instrument Pricing Worksheet", self.pricing_worksheet)
		if ws.docstatus != 1:
			return
		if self.contract_type == "CPT" and not _close(self.revenue_share_pct, ws.required_revenue_share_pct):
			frappe.throw(
				_("Revenue Share % {0} does not match worksheet {1} ({2}).").format(
					frappe.bold(self.revenue_share_pct or 0),
					frappe.bold(ws.name),
					frappe.bold(ws.required_revenue_share_pct or 0),
				)
			)
		for field in ("avg_samples_per_day", "operational_days_per_month"):
			if not _close(self.get(field), ws.get(field)):
				frappe.throw(
					_("{0} does not match worksheet {1}. Change the worksheet, not the contract.").format(
						frappe.bold(self.meta.get_label(field)), frappe.bold(ws.name)
					)
				)
		expected = {(line.item_code, line.test_parameter): line for line in ws.reagent_lines}
		actual = {(line.item_code, line.test_parameter) for line in self.contract_reagent_lines}
		if actual != set(expected):
			frappe.throw(
				_("Contract reagent lines do not match worksheet {0} lines.").format(frappe.bold(ws.name))
			)
		for line in self.contract_reagent_lines:
			src = expected[(line.item_code, line.test_parameter)]
			pairs = [
				("standard_price", src.cogs_per_pack),
				("contract_price", src.selling_price_per_pack),
				("qty_required_total", src.packs_needed),
				("cogs_per_unit", src.cogs_per_pack),
				("agreed_test_price", src.price_per_test or 0),
				("pack_volume_ml", src.pack_volume_ml),
				("bg_consumption_ml_day", src.bg_consumption_ml_day),
				("bg_consumption_ml_month", src.bg_consumption_ml_month),
				("consumption_ml_per_test", src.consumption_ml_per_test),
				("total_consumption_ml_month", src.total_consumption_ml_month),
			]
			for field, want in pairs:
				if not _close(line.get(field), want):
					frappe.throw(
						_("Row {0} ({1}): {2} does not match worksheet {3}.").format(
							line.idx, frappe.bold(line.item_code), frappe.bold(field), frappe.bold(ws.name)
						)
					)
			want_min = (
				ceil(flt(src.monthly_test_volume) / flt(src.tests_per_pack)) if flt(src.tests_per_pack) else 0
			)
			if flt(line.monthly_test_volume) != flt(src.monthly_test_volume) or flt(
				line.min_monthly_qty
			) != flt(want_min):
				frappe.throw(
					_("Row {0} ({1}): volume does not match worksheet {2}.").format(
						line.idx, frappe.bold(line.item_code), frappe.bold(ws.name)
					)
				)
		expected_cons = {line.item_code: line for line in ws.consumable_lines}
		actual_cons = {line.item_code for line in self.contract_consumable_lines}
		if actual_cons != set(expected_cons):
			frappe.throw(
				_("Contract consumable lines do not match worksheet {0} lines.").format(frappe.bold(ws.name))
			)
		for line in self.contract_consumable_lines:
			src = expected_cons[line.item_code]
			for field, want in [
				("standard_price", src.cogs_per_unit),
				("contract_price", 0),
				("qty_required_total", src.total_units_over_term),
				("cogs_per_unit", src.cogs_per_unit),
			]:
				if not _close(line.get(field), want):
					frappe.throw(
						_("Consumable {0}: {1} does not match worksheet {2}.").format(
							frappe.bold(line.item_code), frappe.bold(field), frappe.bold(ws.name)
						)
					)

	@frappe.whitelist()
	def recompute_recovery(self):
		_recompute(self.name)
		self.reload()

	@frappe.whitelist()
	def create_asset_from_stock(self, warehouse: str, serial_no: str):
		from nbs_customization.utils.placement.assets import capitalize_serial_for_placement

		if self.asset:
			frappe.throw(_("Contract already has an Asset linked."))
		if self.docstatus != 0:
			frappe.throw(_("Contract must be in Draft to create an Asset."))
		if not serial_no:
			frappe.throw(_("A Serial No is required to capitalize an analyzer for placement."))

		asset_name = capitalize_serial_for_placement(
			customer=self.customer,
			customer_name=self.customer_name,
			analyzer_pid=self.analyzer_pid,
			warehouse=warehouse,
			serial_no=serial_no,
		)

		self.db_set("asset", asset_name)
		self.db_set("serial_no", serial_no)
		self.reload()

		return asset_name

	def _validate_pricing_worksheet_link(self):
		if not self.pricing_worksheet:
			return
		ws_status = frappe.db.get_value("Instrument Pricing Worksheet", self.pricing_worksheet, "status")
		if ws_status not in ("Approved", "Applied to Contract"):
			frappe.throw(
				frappe._(
					"Linked Pricing Worksheet {0} has status '{1}'. "
					"Only Approved or Applied worksheets can be linked."
				).format(frappe.bold(self.pricing_worksheet), ws_status)
			)

	def _require_pricing_worksheet(self):
		if not self.pricing_worksheet:
			frappe.throw(frappe._("A Pricing Worksheet must be linked before submission."))

	def _require_asset(self):
		if not self.asset or not self.serial_no:
			frappe.throw(
				frappe._("An Asset with Serial No must be capitalized for placement before submission.")
			)

	def _require_contract_lines(self):
		has_reagent = self.contract_reagent_lines and len(self.contract_reagent_lines) > 0
		has_consumable = self.contract_consumable_lines and len(self.contract_consumable_lines) > 0
		if not has_reagent and not has_consumable:
			frappe.throw(
				frappe._(
					"At least one Contract Line (Test Reagent or Consumable) is required before submission."
				)
			)

	def _activate_contract(self):
		self.contract_status = "Active"
		self.db_set("contract_status", "Active")

		if self.asset:
			frappe.db.set_value(
				"Asset",
				self.asset,
				"custom_current_placement_contract",
				self.name,
			)

	def _validate_no_deployment(self):
		deployment = frappe.db.get_value(
			"Analyzer Deployment",
			{"contract": self.name, "deployment_status": ("!=", "Permanently Retrieved")},
			"name",
		)
		if deployment:
			frappe.throw(
				frappe._(
					"Cannot cancel Contract {0} — Analyzer Deployment {1} exists "
					"and has not been permanently retrieved. Retrieve the analyzer first."
				).format(frappe.bold(self.name), frappe.bold(deployment)),
				title=frappe._("Active Deployment Exists"),
			)

	def _clear_asset_link(self):
		if self.asset:
			frappe.db.set_value(
				"Asset",
				self.asset,
				"custom_current_placement_contract",
				None,
			)

	def _link_pricing_worksheet(self):
		if not self.pricing_worksheet:
			return
		ws = frappe.get_doc("Instrument Pricing Worksheet", self.pricing_worksheet)
		if ws.linked_contract and ws.linked_contract != self.name:
			frappe.throw(
				frappe._(
					"Pricing Worksheet {0} is already linked to Contract {1}. "
					"Unlink it first before submitting this contract."
				).format(frappe.bold(self.pricing_worksheet), frappe.bold(ws.linked_contract))
			)
		ws.db_set("status", "Applied to Contract")
		ws.db_set("linked_contract", self.name)

	def _unlink_pricing_worksheet(self):
		if not self.pricing_worksheet:
			return
		ws = frappe.get_doc("Instrument Pricing Worksheet", self.pricing_worksheet)
		if ws.linked_contract == self.name:
			ws.db_set("status", "Approved")
			ws.db_set("linked_contract", None)


def _close(a, b, tol=0.01):
	"""Numeric equality within print rounding."""
	return abs(flt(a) - flt(b)) <= tol


def _create_contract_price_list(contract):
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

	for line in contract.contract_reagent_lines:
		if (line.contract_price or 0) > 0:
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"price_list": pl.name,
					"item_code": line.item_code,
					"price_list_rate": line.contract_price,
					"uom": frappe.db.get_value("Item", line.item_code, "stock_uom"),
					"selling": 1,
					"valid_from": frappe.utils.today(),
				}
			).insert(ignore_permissions=True)

	return pl
