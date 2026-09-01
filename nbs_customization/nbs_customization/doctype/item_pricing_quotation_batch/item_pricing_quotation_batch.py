# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, today

from nbs_customization.utils.pricing import allocate_shared_costs, get_exchange_rate


class ItemPricingQuotationBatch(Document):
	def validate(self):
		self._set_company_currency_and_rate()
		self._validate_items()
		allocate_shared_costs(self)
		self._compute_totals()

	def before_submit(self):
		self._validate_items()
		allocate_shared_costs(self)
		if not self.items:
			frappe.throw("Add at least one item.")
		for row in self.items:
			if not flt(row.true_cost_per_unit):
				frappe.throw(f"True cost not computed for {row.item_code}. Check shared costs and qty.")

	def on_submit(self):
		# audit: create/update Item Pricing Settings + Item Price tiers per row
		for row in self.items:
			try:
				_ensure_pricing_settings_for_batch_row(self, row)
			except Exception:
				frappe.log_error(
					message=frappe.get_traceback(),
					title=f"Pricing batch apply failed: {row.item_code} ({self.name})",
				)
				frappe.throw(f"Failed to apply pricing for {row.item_code}. Check Error Log.")

	def on_cancel(self):
		# history kept; just add comment
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": self.doctype,
				"reference_name": self.name,
				"content": f"Batch {self.name} cancelled — Item Price history retained.",
			}
		).insert(ignore_permissions=True)

	# ── helpers ───────────────────────────────────────────────────────────────

	def _set_company_currency_and_rate(self):
		if not self.company:
			return
		if not self.company_currency:
			self.company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		if not self.exchange_rate_date:
			self.exchange_rate_date = self.posting_date or today()
		if self.quote_currency and self.company_currency:
			if self.quote_currency == self.company_currency:
				self.exchange_rate = 1
			elif not flt(self.exchange_rate):
				fetched = get_exchange_rate(
					self.quote_currency, self.company_currency, self.exchange_rate_date
				)
				if fetched:
					self.exchange_rate = fetched

	def _validate_items(self):
		if not self.items:
			return
		for row in self.items:
			if not row.item_code:
				frappe.throw("Item Code is required in every row.")
			if flt(row.qty) <= 0:
				frappe.throw(f"Qty must be > 0 for {row.item_code}.")
			if flt(row.target_margin_pct) <= 0 or flt(row.target_margin_pct) >= 100:
				frappe.throw(f"Target Margin must be 0-100 for {row.item_code}.")

	def _compute_totals(self):
		self.total_base = flt(sum(flt(r.base_total) for r in self.items), 2)
		self.total_true_cost = flt(sum(flt(r.true_cost) for r in self.items), 2)
		self.total_final = flt(sum(flt(r.final_total) for r in self.items), 2)


def _ensure_pricing_settings_for_batch_row(batch, row):
	"""
	Create or update Item Pricing Settings (Manual) for row.item_code,
	then bulk-apply tier Item Price rows including FX secondary if configured.
	"""
	existing = frappe.db.get_value("Item Pricing Settings", {"item_code": row.item_code}, "name")
	uom = frappe.get_cached_value("Item", row.item_code, "sales_uom") or frappe.get_cached_value(
		"Item", row.item_code, "stock_uom"
	)

	# map tiers from row
	tiers = {
		"basic_rate": row.basic_rate,
		"rate_15": row.rate_15,
		"rate_30": row.rate_30,
		"rate_45": row.rate_45,
		"rate_commission": row.rate_commission,
		"rate_commission_tax": row.rate_commission_tax,
		"final_rate_per_unit": row.final_rate_per_unit,
	}

	# standard rate for Standard Selling = source tier (batch-level)
	source_map = {
		"Basic": row.basic_rate,
		"15%": row.rate_15,
		"30%": row.rate_30,
		"45%": row.rate_45,
		"Commission": row.rate_commission,
		"Commission (Tax)": row.rate_commission_tax,
	}
	standard_rate = flt(source_map.get(batch.standard_selling_source_tier or "30%"), 2) or flt(row.rate_30, 2)

	if existing:
		doc = frappe.get_doc("Item Pricing Settings", existing)
		doc.pricing_mode = "Manual"
		doc.target_margin_pct = row.target_margin_pct
		doc.commission_pct = batch.commission_pct
		doc.wht_pct = batch.wht_pct
		doc.standard_selling_source_tier = batch.standard_selling_source_tier
		doc.quote_currency = batch.quote_currency
		doc.company_currency = batch.company_currency
		doc.exchange_rate = batch.exchange_rate
		doc.exchange_rate_date = batch.exchange_rate_date
		doc.estimated_base_rate = row.unit_cost
		doc.manual_qty = row.qty
		doc.manual_true_cost = row.true_cost_per_unit
		doc.basic_rate = tiers["basic_rate"]
		doc.rate_15 = tiers["rate_15"]
		doc.rate_30 = tiers["rate_30"]
		doc.rate_45 = tiers["rate_45"]
		doc.rate_commission = tiers["rate_commission"]
		doc.rate_commission_tax = tiers["rate_commission_tax"]
		doc.final_rate_per_unit = tiers["final_rate_per_unit"]
		doc.suggested_selling_price = standard_rate
		doc.price_list_basic = batch.price_list_basic
		doc.price_list_15 = batch.price_list_15
		doc.price_list_30 = batch.price_list_30
		doc.price_list_45 = batch.price_list_45
		doc.price_list_commission = batch.price_list_commission
		doc.price_list_commission_tax = batch.price_list_commission_tax
		doc.reference_quotation_batch = batch.name
		doc.flags.ignore_permissions = True
		doc.save()
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Item Pricing Settings",
				"item_code": row.item_code,
				"pricing_mode": "Manual",
				"target_margin_pct": row.target_margin_pct,
				"commission_pct": batch.commission_pct,
				"wht_pct": batch.wht_pct,
				"standard_selling_source_tier": batch.standard_selling_source_tier,
				"quote_currency": batch.quote_currency,
				"company_currency": batch.company_currency,
				"exchange_rate": batch.exchange_rate,
				"exchange_rate_date": batch.exchange_rate_date,
				"estimated_base_rate": row.unit_cost,
				"manual_qty": row.qty,
				"manual_true_cost": row.true_cost_per_unit,
				"basic_rate": tiers["basic_rate"],
				"rate_15": tiers["rate_15"],
				"rate_30": tiers["rate_30"],
				"rate_45": tiers["rate_45"],
				"rate_commission": tiers["rate_commission"],
				"rate_commission_tax": tiers["rate_commission_tax"],
				"final_rate_per_unit": tiers["final_rate_per_unit"],
				"suggested_selling_price": standard_rate,
				"price_list_basic": batch.price_list_basic,
				"price_list_15": batch.price_list_15,
				"price_list_30": batch.price_list_30,
				"price_list_45": batch.price_list_45,
				"price_list_commission": batch.price_list_commission,
				"price_list_commission_tax": batch.price_list_commission_tax,
				"reference_quotation_batch": batch.name,
			}
		)
		doc.insert(ignore_permissions=True)

	# now write Item Price tiers (6) + FX secondary if needed
	_apply_tiers_from_batch(batch, row, doc, uom, standard_rate)


def _apply_tiers_from_batch(batch, row, settings_doc, uom, standard_rate):
	"""Bulk upsert Item Price per tier, including dual-currency secondary lists if FX."""
	tier_price_lists = {
		"basic": (row.basic_rate, batch.price_list_basic),
		"15": (row.rate_15, batch.price_list_15),
		"30": (standard_rate, batch.price_list_30),
		"45": (row.rate_45, batch.price_list_45),
		"commission": (row.rate_commission, batch.price_list_commission),
		"commission_tax": (row.rate_commission_tax, batch.price_list_commission_tax),
	}
	secondary_map = {
		"basic": batch.price_list_basic_secondary,
		"15": batch.price_list_15_secondary,
		"30": batch.price_list_30_secondary,
		"45": batch.price_list_45_secondary,
		"commission": batch.price_list_commission_secondary,
		"commission_tax": batch.price_list_commission_tax_secondary,
	}

	for tier_key, (rate, pl) in tier_price_lists.items():
		if not pl or not flt(rate):
			continue
		currency = frappe.get_cached_value("Price List", pl, "currency")
		existing = frappe.db.get_value(
			"Item Price", {"item_code": row.item_code, "price_list": pl, "selling": 1}, "name"
		)
		if existing:
			frappe.db.set_value(
				"Item Price",
				existing,
				{"price_list_rate": flt(rate, 2), "currency": currency, "valid_from": today()},
				update_modified=True,
			)
		else:
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": row.item_code,
					"price_list": pl,
					"price_list_rate": flt(rate, 2),
					"currency": currency,
					"uom": uom,
					"valid_from": today(),
					"selling": 1,
					"buying": 0,
				}
			).insert(ignore_permissions=True)

		# FX dual write if secondary list configured and rate differs
		sec_pl = secondary_map.get(tier_key)
		if sec_pl and batch.quote_currency != batch.company_currency and flt(batch.exchange_rate):
			converted = flt(rate * flt(batch.exchange_rate), 2)
			currency2 = frappe.get_cached_value("Price List", sec_pl, "currency")
			existing2 = frappe.db.get_value(
				"Item Price", {"item_code": row.item_code, "price_list": sec_pl, "selling": 1}, "name"
			)
			if existing2:
				frappe.db.set_value(
					"Item Price",
					existing2,
					{"price_list_rate": converted, "currency": currency2, "valid_from": today()},
					update_modified=True,
				)
			else:
				frappe.get_doc(
					{
						"doctype": "Item Price",
						"item_code": row.item_code,
						"price_list": sec_pl,
						"price_list_rate": converted,
						"currency": currency2,
						"uom": uom,
						"valid_from": today(),
						"selling": 1,
						"buying": 0,
					}
				).insert(ignore_permissions=True)

	# update live current_selling_price on settings
	frappe.db.set_value(
		"Item Pricing Settings",
		settings_doc.name,
		"current_selling_price",
		flt(standard_rate, 2),
		update_modified=False,
	)
