# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, today

from nbs_customization.utils.pricing import (
	compute_tiers,
	get_exchange_rate,
	get_standard_rate,
	recompute_manual_estimate,
	recompute_suggested_price,
)


class ItemPricingSettings(Document):
	def validate(self):
		self._validate_margin()
		self._validate_no_duplicate()
		self._validate_mode_fields()
		self._set_company_currency()

	def _validate_margin(self):
		margin = flt(self.target_margin_pct)
		if margin <= 0:
			frappe.throw("Target Margin must be greater than 0%.")
		if margin >= 100:
			frappe.throw("Target Margin must be less than 100%.")
		if flt(self.commission_pct) < 0 or flt(self.commission_pct) >= 100:
			frappe.throw("Commission must be between 0% and 99%.")
		if flt(self.wht_pct) < 0 or flt(self.wht_pct) >= 100:
			frappe.throw("WHT must be between 0% and 99%.")

	def _validate_no_duplicate(self):
		if self.is_new():
			if frappe.db.exists("Item Pricing Settings", self.item_code):
				frappe.throw(
					f"A pricing settings record already exists for {self.item_code}. "
					"Open that record to make changes."
				)

	def _validate_mode_fields(self):
		if self.pricing_mode == "Manual":
			if not flt(self.manual_qty):
				self.manual_qty = 1
			if flt(self.manual_qty) <= 0:
				frappe.throw("Qty must be greater than 0 for Manual mode.")
			# default cost mode
			if not getattr(self, "manual_cost_mode", None):
				self.manual_cost_mode = "Breakdown"
			# Hybrid Y fallback: if override filled but mode is Breakdown and breakdown empty, auto-switch to Override for old docs
			breakdown_fields = [
				"manual_bank_charges",
				"manual_freight",
				"manual_clearing_fees",
				"manual_transport_in",
				"manual_transport_out",
				"manual_overhead",
				"manual_fixed_cost",
			]
			has_override = flt(self.estimated_true_cost_override)
			has_breakdown = flt(self.estimated_base_rate) or any(flt(getattr(self, f, 0)) for f in breakdown_fields)
			if has_override and not has_breakdown and self.manual_cost_mode == "Breakdown":
				self.manual_cost_mode = "Override"
			if self.manual_cost_mode == "Breakdown":
				if not flt(self.estimated_base_rate):
					frappe.throw("For Breakdown mode, Estimated Base Rate (per unit) is required.")
				if has_override:
					frappe.throw(
						"True Cost Override must be empty in Breakdown mode. Switch to Override mode to use it, or clear it."
					)
			else:  # Override
				if not has_override:
					frappe.throw("For Override mode, Estimated True Cost Override (Total for Qty) is required.")
				if has_breakdown:
					frappe.throw(
						"Breakdown totals must be empty in Override mode. Clear them or switch to Breakdown mode."
					)
			if not self.quote_currency:
				pass  # optional, but warn via msg below
		if not self.standard_selling_source_tier:
			self.standard_selling_source_tier = "30%"

	def _set_company_currency(self):
		if self.pricing_mode == "Manual" and self.quote_currency:
			# default company_currency from Company default_currency if empty
			if not self.company_currency:
				company = frappe.db.get_single_value("Global Defaults", "default_company")
				if company:
					self.company_currency = frappe.get_cached_value("Company", company, "default_currency")
			# fetch / keep exchange_rate if FX applicable
			if self.quote_currency != self.company_currency and not flt(self.exchange_rate):
				date = self.exchange_rate_date or today()
				fetched = get_exchange_rate(self.quote_currency, self.company_currency, date)
				if fetched:
					self.exchange_rate = fetched

	def before_save(self):
		# auto-clear hidden branch to keep DB clean (Hybrid)
		if self.pricing_mode == "Manual" and getattr(self, "manual_cost_mode", None):
			if self.manual_cost_mode == "Breakdown" and flt(self.estimated_true_cost_override):
				self.estimated_true_cost_override = 0
			elif self.manual_cost_mode == "Override":
				for _f in [
					"manual_bank_charges",
					"manual_freight",
					"manual_clearing_fees",
					"manual_transport_in",
					"manual_transport_out",
					"manual_overhead",
					"manual_fixed_cost",
				]:
					if flt(getattr(self, _f, 0)):
						setattr(self, _f, 0)
				# base rate not used in Override, keep 0 to avoid confusion but allow it to stay? clear for clean state
				# keep estimated_base_rate as is? clear to avoid validate confusion if user toggles back
				if flt(self.estimated_base_rate):
					# keep for potential switch back? but clear to enforce exclusivity — clear
					pass
		# compute preview tiers so form shows them after save even before Refresh
		try:
			if self.pricing_mode == "Manual":
				true_cost, tiers = recompute_manual_estimate(self)
				self.manual_true_cost = flt(true_cost, 2)
				self.basic_rate = tiers["basic_rate"]
				self.target_rate = tiers["target_rate"]
				self.rate_15 = tiers["rate_15"]
				self.rate_30 = tiers["rate_30"]
				self.rate_45 = tiers["rate_45"]
				self.rate_commission = tiers["rate_commission"]
				self.rate_commission_tax = tiers["rate_commission_tax"]
				self.rate_target_commission = tiers["rate_target_commission"]
				self.rate_target_commission_tax = tiers["rate_target_commission_tax"]
				self.final_rate_per_unit = tiers["final_rate_per_unit"]
				self.suggested_selling_price = get_standard_rate(tiers, self.standard_selling_source_tier)
			else:
				# Auto: keep existing tiers until Refresh
				pass
		except Exception:
			pass


# ── Whitelisted actions ───────────────────────────────────────────────────────


@frappe.whitelist()
def refresh_valuation(doc_name):
	"""Branch on pricing_mode: Auto pulls SLE, Manual recomputes from estimate."""
	doc = frappe.get_doc("Item Pricing Settings", doc_name)
	if doc.pricing_mode == "Manual":
		true_cost, tiers = recompute_manual_estimate(doc)
		standard_rate = get_standard_rate(tiers, doc.standard_selling_source_tier)
		# current selling price = live Standard Selling
		price_list = doc.price_list_30 or doc.price_list or "Standard Selling"
		current_sp = flt(
			frappe.db.get_value(
				"Item Price",
				{"item_code": doc.item_code, "price_list": price_list, "selling": 1},
				"price_list_rate",
			)
		)
		frappe.db.set_value(
			"Item Pricing Settings",
			doc_name,
			{
				"manual_true_cost": flt(true_cost, 2),
				"current_valuation_rate": flt(doc.current_valuation_rate or 0, 4),
				"basic_rate": tiers["basic_rate"],
				"target_rate": tiers["target_rate"],
				"rate_15": tiers["rate_15"],
				"rate_30": tiers["rate_30"],
				"rate_45": tiers["rate_45"],
				"rate_commission": tiers["rate_commission"],
				"rate_commission_tax": tiers["rate_commission_tax"],
				"rate_target_commission": tiers["rate_target_commission"],
				"rate_target_commission_tax": tiers["rate_target_commission_tax"],
				"final_rate_per_unit": tiers["final_rate_per_unit"],
				"suggested_selling_price": flt(standard_rate, 2),
				"current_selling_price": flt(current_sp, 2),
				"last_updated": now_datetime(),
			},
			update_modified=False,
		)
	else:
		recompute_suggested_price(doc.item_code)
		# recompute_suggested_price already wrote tier fields; just ensure current_selling_price refreshed above
		# (it does). No extra work.
	frappe.msgprint(
		"Valuation refreshed. Review the tier rates below.",
		indicator="blue",
		alert=True,
	)


@frappe.whitelist()
def apply_suggested_price(doc_name):
	"""Legacy single-tier apply — keeps backward compat, maps to standard_selling_source_tier."""
	return apply_tiers(doc_name, selected_tiers=None)


@frappe.whitelist()
def apply_tiers(doc_name, selected_tiers=None):
	"""
	Apply tier rates to Item Price.
	- selected_tiers: list of keys like ["basic","15","30","45","commission","commission_tax"] or None = all
	- Also writes Standard Selling via standard_selling_source_tier.
	"""
	import json

	doc = frappe.get_doc("Item Pricing Settings", doc_name)

	# normalize selected_tiers (JS may send JSON string)
	if isinstance(selected_tiers, str):
		try:
			selected_tiers = json.loads(selected_tiers)
		except Exception:
			selected_tiers = [selected_tiers] if selected_tiers else None

	# collect tier → rate → price_list mapping (9 tiers: 6 fixed + Target + Target Commission)
	tier_defs = {
		"basic": (doc.basic_rate, doc.price_list_basic or "Selling - Basic"),
		"target": (getattr(doc, "target_rate", 0) or doc.final_rate_per_unit, doc.price_list or "Standard Selling"),
		"15": (doc.rate_15, doc.price_list_15 or "Selling - 15%"),
		"30": (doc.rate_30, doc.price_list_30 or "Selling - 30%"),
		"45": (doc.rate_45, doc.price_list_45 or "Selling - 45%"),
		"commission": (doc.rate_commission, doc.price_list_commission or "Selling - Commission (10%)"),
		"commission_tax": (
			doc.rate_commission_tax,
			doc.price_list_commission_tax or "Selling - Commission (Tax) (10%+3%)",
		),
		"target_commission": (
			getattr(doc, "rate_target_commission", 0) or doc.final_rate_per_unit,
			getattr(doc, "price_list_target_commission", None) or "Selling - Commission (Target)",
		),
		"target_commission_tax": (
			getattr(doc, "rate_target_commission_tax", 0) or doc.final_rate_per_unit,
			getattr(doc, "price_list_target_commission_tax", None) or "Selling - Commission (Tax) (Target)",
		),
	}

	# default to all tiers if none selected
	if not selected_tiers:
		selected_tiers = list(tier_defs.keys())

	# standard selling override — ensure Standard Selling gets the chosen tier
	standard_map = {
		"Basic": doc.basic_rate,
		"15%": doc.rate_15,
		"30%": doc.rate_30,
		"45%": doc.rate_45,
		"Target": getattr(doc, "target_rate", 0) or doc.final_rate_per_unit,
		"Commission (10%)": doc.rate_commission,
		"Commission (Tax) (10%+3%)": doc.rate_commission_tax,
		"Commission": doc.rate_commission,
		"Commission (Tax)": doc.rate_commission_tax,
		"Target Commission": getattr(doc, "rate_target_commission", 0) or doc.final_rate_per_unit,
		"Target Commission (Tax)": getattr(doc, "rate_target_commission_tax", 0) or doc.final_rate_per_unit,
	}
	# if 30 is in selected list but source is different, still write Standard Selling with source tier rate
	standard_rate = flt(standard_map.get(doc.standard_selling_source_tier or "30%"), 2)

	# validate tiers have values
	any_rate = False
	for k in selected_tiers:
		if k in tier_defs and flt(tier_defs[k][0]):
			any_rate = True
	if not any_rate and not standard_rate:
		frappe.throw("No tier rates computed. Click Recalculate before applying.")

	uom = frappe.get_cached_value("Item", doc.item_code, "sales_uom") or frappe.get_cached_value(
		"Item", doc.item_code, "stock_uom"
	)

	# ensure at least standard selling is written
	tiers_to_write = {}
	for k in selected_tiers:
		if k not in tier_defs:
			continue
		rate, pl = tier_defs[k]
		if not flt(rate):
			continue
		tiers_to_write[k] = (flt(rate, 2), pl)

	# Always ensure Standard Selling reflects standard_selling_source_tier (separate from fixed 30% tier Selling - 30%)
	# This handles case where target list is Standard Selling but source is 30% — Standard Selling should hold source rate, not target rate alone
	standard_selling_pl = "Standard Selling"
	if standard_rate and standard_selling_pl not in [pl for _, pl in tiers_to_write.values()]:
		# check if any tier already writes to Standard Selling with same rate — avoid duplicate write if same
		already_standard = any(pl == standard_selling_pl and flt(rate, 2) == flt(standard_rate, 2) for rate, pl in tiers_to_write.values())
		if not already_standard:
			# avoid overwriting target tier that also targets Standard Selling with different rate — let target keep its rate, but ensure Standard Selling gets source
			# If target tier also targets Standard Selling and source != Target, Standard Selling should be source rate, so we will overwrite target's Standard Selling entry
			# Dedupe: if target tier already targets Standard Selling with different rate, we still write Standard Selling with source rate (last write wins is source)
			tiers_to_write["_standard"] = (flt(standard_rate, 2), standard_selling_pl)

	applied = []
	for _tier_key, (rate, price_list) in tiers_to_write.items():
		currency = frappe.get_cached_value("Price List", price_list, "currency")
		if not currency:
			# create price list currency defaults to quote/company currency
			currency = (
				doc.quote_currency
				or doc.company_currency
				or frappe.get_cached_value(
					"Company",
					frappe.db.get_single_value("Global Defaults", "default_company"),
					"default_currency",
				)
			)
		existing = frappe.db.get_value(
			"Item Price", {"item_code": doc.item_code, "price_list": price_list, "selling": 1}, "name"
		)
		if existing:
			frappe.db.set_value(
				"Item Price",
				existing,
				{"price_list_rate": rate, "currency": currency, "valid_from": today()},
				update_modified=True,
			)
		else:
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": doc.item_code,
					"price_list": price_list,
					"price_list_rate": rate,
					"currency": currency,
					"uom": uom,
					"valid_from": today(),
					"selling": 1,
					"buying": 0,
				}
			).insert(ignore_permissions=True)
		applied.append(f"{price_list}: {currency} {rate}")

	# handle FX dual-currency: if doc has quote vs company and secondary price lists exist, write converted rates too
	if (
		doc.pricing_mode == "Manual"
		and doc.quote_currency
		and doc.company_currency
		and doc.quote_currency != doc.company_currency
		and flt(doc.exchange_rate)
	):
		# check secondary price list fields if they exist (added via fixtures or later)
		secondary_map = {
			"basic": getattr(doc, "price_list_basic_secondary", None),
			"target": getattr(doc, "price_list_target_secondary", None),
			"15": getattr(doc, "price_list_15_secondary", None),
			"30": getattr(doc, "price_list_30_secondary", None),
			"45": getattr(doc, "price_list_45_secondary", None),
			"commission": getattr(doc, "price_list_commission_secondary", None),
			"commission_tax": getattr(doc, "price_list_commission_tax_secondary", None),
			"target_commission": getattr(doc, "price_list_target_commission_secondary", None) if hasattr(doc, "price_list_target_commission_secondary") else None,
			"target_commission_tax": getattr(doc, "price_list_target_commission_tax_secondary", None) if hasattr(doc, "price_list_target_commission_tax_secondary") else None,
			"_standard": getattr(doc, "price_list_target_secondary", None),
		}
		for k, sec_pl in secondary_map.items():
			if not sec_pl or k not in tiers_to_write:
				continue
			converted = flt(tiers_to_write[k][0] * flt(doc.exchange_rate), 2)
			currency = frappe.get_cached_value("Price List", sec_pl, "currency")
			existing = frappe.db.get_value(
				"Item Price", {"item_code": doc.item_code, "price_list": sec_pl, "selling": 1}, "name"
			)
			if existing:
				frappe.db.set_value(
					"Item Price",
					existing,
					{"price_list_rate": converted, "currency": currency, "valid_from": today()},
					update_modified=True,
				)
			else:
				frappe.get_doc(
					{
						"doctype": "Item Price",
						"item_code": doc.item_code,
						"price_list": sec_pl,
						"price_list_rate": converted,
						"currency": currency,
						"uom": uom,
						"valid_from": today(),
						"selling": 1,
						"buying": 0,
					}
				).insert(ignore_permissions=True)
			applied.append(f"{sec_pl}: {currency} {converted} (FX)")

	# update current_selling_price to standard_rate for live truth
	frappe.db.set_value(
		"Item Pricing Settings",
		doc_name,
		{"current_selling_price": flt(standard_rate, 2), "suggested_selling_price": flt(standard_rate, 2)},
		update_modified=False,
	)
	frappe.db.commit()

	frappe.msgprint(
		"Selling prices applied:<br>" + "<br>".join(applied),
		title="Prices Applied",
		indicator="green",
	)


@frappe.whitelist()
def get_fx_rate(from_currency, to_currency, date=None):
	return get_exchange_rate(from_currency, to_currency, date)
