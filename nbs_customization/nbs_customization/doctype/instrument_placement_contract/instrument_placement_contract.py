# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from nbs_customization.utils.placement.recovery import recompute_contract_recovery as _recompute
from nbs_customization.utils.placement.valid_items import validate_items_belong_to_analyzer


class InstrumentPlacementContract(Document):
	def validate(self):
		self._validate_contract_lines()
		self._compute_duration()
		self._compute_min_monthly_value()
		self._compute_cpt_fields()
		self._validate_pricing_worksheet_link()

	def before_submit(self):
		self._require_contract_lines()
		self._require_pricing_worksheet()

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

	@frappe.whitelist()
	def recompute_recovery(self):
		_recompute(self.name)
		self.reload()

	@frappe.whitelist()
	def create_asset_from_stock(self, warehouse, serial_no):
		if self.asset:
			frappe.throw(_("Contract already has an Asset linked."))
		if self.docstatus != 0:
			frappe.throw(_("Contract must be in Draft to create an Asset."))

		serial_doc = frappe.get_doc("Serial No", serial_no)
		if serial_doc.item_code != self.analyzer_pid:
			frappe.throw(_("Serial No {0} does not match analyzer {1}.").format(serial_no, self.analyzer_pid))
		if serial_doc.status != "In Store" or serial_doc.warehouse != warehouse:
			frappe.throw(_("Serial No {0} is not available in warehouse {1}.").format(serial_no, warehouse))

		capital_item = "Capital Asset"
		if not frappe.db.exists("Item", capital_item):
			frappe.throw(
				_("Capital asset item '{0}' not found. Run migrate to create it.").format(capital_item)
			)

		company = (
			frappe.db.get_value("Instrument Pricing Worksheet", self.pricing_worksheet, "company")
			or frappe.defaults.get_defaults().company
		)

		asset_category = frappe.db.get_value("Item", capital_item, "asset_category")
		if not asset_category:
			frappe.throw(
				_("Item {0} has no Asset Category set. Set one on the Item master.").format(capital_item)
			)

		instrument_spec = frappe.db.get_value("Item", self.analyzer_pid, "custom_instrument_specification")

		asset = frappe.get_doc(
			{
				"doctype": "Asset",
				"asset_name": "{0} - {1}".format(self.customer_name or self.customer, serial_doc.serial_no),
				"item_code": capital_item,
				"company": company,
				"asset_category": asset_category,
				"location": self.customer_site,
				"custom_serial_no": serial_no,
				"custom_instrument_specification": instrument_spec,
				"custom_current_deployment_status": "Warehouse",
				"gross_purchase_amount": serial_doc.purchase_rate or 0,
				"purchase_date": frappe.utils.today(),
				"asset_type": "Composite Asset",
			}
		).insert(ignore_permissions=True)

		cap = frappe.get_doc(
			{
				"doctype": "Asset Capitalization",
				"company": company,
				"target_asset": asset.name,
				"posting_date": frappe.utils.today(),
				"stock_items": [
					{
						"item_code": self.analyzer_pid,
						"warehouse": warehouse,
						"stock_qty": 1,
						"use_serial_batch_fields": 1,
						"serial_no": serial_doc.serial_no,
					}
				],
			}
		)
		cap.insert(ignore_permissions=True)
		cap.submit()

		asset.reload()
		asset.submit()

		self.db_set("asset", asset.name)
		self.db_set("serial_no", serial_doc.serial_no)
		self.reload()

		return asset.name

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
