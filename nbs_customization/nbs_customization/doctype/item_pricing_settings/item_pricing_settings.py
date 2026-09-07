# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, today

from nbs_customization.utils.pricing import (
	FIXED_TIER_SET,
	compute_tiers,
	get_exchange_rate,
	get_standard_rate,
	recompute_manual_estimate,
	recompute_suggested_price,
)


class ItemPricingSettings(Document):
	def validate(self):
		self._validate_target_pairs()
		self._validate_source_tier()
		self._validate_no_duplicate()
		self._validate_no_duplicate_price_lists()
		self._validate_cost_conversion()
		self._validate_mode_fields()
		self._set_company_currency()
		# ensure fixed tier lists are correct (read_only)
		self._ensure_fixed_tier_lists()

	def _ensure_fixed_tier_lists(self):
		if self.price_list_basic != "Selling - Basic":
			self.price_list_basic = "Selling - Basic"
		if self.price_list_15 != "Selling - 15%":
			self.price_list_15 = "Selling - 15%"
		if self.price_list_30 != "Selling - 30%":
			self.price_list_30 = "Selling - 30%"
		if self.price_list_45 != "Selling - 45%":
			self.price_list_45 = "Selling - 45%"
		if self.price_list_commission != "Selling - Commission":
			self.price_list_commission = "Selling - Commission"
		if self.price_list_commission_tax != "Selling - Commission (Tax)":
			self.price_list_commission_tax = "Selling - Commission (Tax)"

	def _validate_target_pairs(self):
		# target margin pair
		margin = flt(self.target_margin_pct)
		has_margin = margin > 0
		has_margin_list = bool(self.price_list)
		if has_margin:
			if margin >= 100:
				frappe.throw(_("Target Margin must be less than 100%."))
			if not has_margin_list:
				frappe.throw(_("Price List — Target Margin is required when Target Margin % is set."))
			if self.price_list in FIXED_TIER_SET:
				frappe.throw(
					_("Price List — Target Margin cannot be one of the 6 fixed tier lists: {0}").format(
						self.price_list
					)
				)
		elif has_margin_list:
			frappe.throw(_("Target Margin % is required when Price List — Target Margin is set."))
		# commission pair — blank/0 treated as not-set, 0 not allowed
		comm = flt(self.commission_pct)
		has_comm = comm > 0
		has_comm_list = bool(self.price_list_target_commission)
		if has_comm:
			if comm >= 100:
				frappe.throw(_("Target Commission must be less than 100%."))
			if comm < 1:
				frappe.throw(_("Target Commission must be blank or 1-99%. 0% is not allowed."))
			if not has_comm_list:
				frappe.throw(_("Price List — Target Commission is required when Target Commission % is set."))
			if self.price_list_target_commission in FIXED_TIER_SET:
				frappe.throw(
					_("Price List — Target Commission cannot be one of the 6 fixed tier lists: {0}").format(
						self.price_list_target_commission
					)
				)
		elif has_comm_list:
			frappe.throw(_("Target Commission % is required when Price List — Target Commission is set."))
		# WHT pair
		wht = flt(self.wht_pct)
		has_wht = wht > 0
		has_wht_list = bool(self.price_list_target_commission_tax)
		if has_wht:
			if wht >= 100:
				frappe.throw(_("Target WHT must be less than 100%."))
			if wht < 1:
				frappe.throw(_("Target WHT must be blank or 1-99%. 0% is not allowed."))
			if not has_wht_list:
				frappe.throw(_("Price List — Target Commission (Tax) is required when Target WHT % is set."))
			if self.price_list_target_commission_tax in FIXED_TIER_SET:
				frappe.throw(
					_(
						"Price List — Target Commission (Tax) cannot be one of the 6 fixed tier lists: {0}"
					).format(self.price_list_target_commission_tax)
				)
		elif has_wht_list:
			frappe.throw(_("Target WHT % is required when Price List — Target Commission (Tax) is set."))

	def _validate_source_tier(self):
		source = self.standard_selling_source_tier or "30%"
		if source == "Target" and not flt(self.target_margin_pct):
			frappe.throw(_("Standard Selling Source Tier is Target but Target Margin % is not set."))
		if source == "Target Commission" and not flt(self.commission_pct):
			frappe.throw(
				_("Standard Selling Source Tier is Target Commission but Target Commission % is not set.")
			)
		if source == "Target Commission (Tax)" and (not flt(self.commission_pct) or not flt(self.wht_pct)):
			frappe.throw(
				_(
					"Standard Selling Source Tier is Target Commission (Tax) but Target Commission % or WHT % is not set."
				)
			)

	def _validate_no_duplicate_price_lists(self):
		lists = [
			("Price List — Target Margin", self.price_list),
			("Price List — Target Commission", self.price_list_target_commission),
			("Price List — Target Commission (Tax)", self.price_list_target_commission_tax),
		]
		seen = {}
		for label, name in lists:
			if not name:
				continue
			if name in seen:
				frappe.throw(
					_(
						"Price List {0} is used for both {1} and {2}. Please choose distinct Price Lists."
					).format(name, seen[name], label)
				)
			# also not in fixed set
			if name in FIXED_TIER_SET:
				frappe.throw(
					_("Price List {0} for {1} cannot be one of the 6 fixed tier lists.").format(name, label)
				)
			seen[name] = label
		# distinct among themselves — already checked above

	def _validate_cost_conversion(self):
		# Only for Manual
		if self.pricing_mode != "Manual":
			return
		cost_ccy = getattr(self, "cost_currency", None)
		company_ccy = getattr(self, "company_currency", None)
		if cost_ccy and company_ccy and cost_ccy != company_ccy:
			if not flt(self.exchange_rate):
				frappe.throw(
					_("Exchange Rate (Cost → Company) is required when Cost Currency != Company Currency.")
				)
		# If same currency, ensure convert flags are off (auto-clear for cleanliness)
		if cost_ccy and company_ccy and cost_ccy == company_ccy:
			for f in [
				"convert_estimated_base_rate",
				"convert_manual_bank_charges",
				"convert_manual_freight",
				"convert_manual_clearing_fees",
				"convert_manual_transport_in",
				"convert_manual_transport_out",
				"convert_manual_overhead",
				"convert_manual_fixed_cost",
				"convert_estimated_true_cost_override",
			]:
				if getattr(self, f, 0):
					setattr(self, f, 0)
			if flt(self.exchange_rate) != 1:
				self.exchange_rate = 1

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
			has_breakdown = flt(self.estimated_base_rate) or any(
				flt(getattr(self, f, 0)) for f in breakdown_fields
			)
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
					frappe.throw(
						"For Override mode, Estimated True Cost Override (Total for Qty) is required."
					)
				if has_breakdown:
					frappe.throw(
						"Breakdown totals must be empty in Override mode. Clear them or switch to Breakdown mode."
					)
		if not self.standard_selling_source_tier:
			self.standard_selling_source_tier = "30%"

	def _set_company_currency(self):
		# Legacy: copy old quote_currency → cost_currency if cost blank (migrated column)
		if not getattr(self, "cost_currency", None) and self.name:
			try:
				res = frappe.db.sql(
					"SELECT `quote_currency` FROM `tabItem Pricing Settings` WHERE name=%s", (self.name,)
				)
				if res and res[0] and res[0][0]:
					self.cost_currency = res[0][0]
			except Exception:
				pass
		# For Manual, ensure company_currency and exchange_rate
		if self.pricing_mode == "Manual" and getattr(self, "cost_currency", None):
			if not self.company_currency:
				company = frappe.db.get_single_value("Global Defaults", "default_company")
				if company:
					self.company_currency = frappe.get_cached_value("Company", company, "default_currency")
			cost_ccy = getattr(self, "cost_currency", None)
			company_ccy = getattr(self, "company_currency", None)
			if cost_ccy and company_ccy:
				if cost_ccy == company_ccy:
					self.exchange_rate = 1
				elif not flt(self.exchange_rate):
					date = self.exchange_rate_date or today()
					fetched = get_exchange_rate(cost_ccy, company_ccy, date)
					if fetched:
						self.exchange_rate = fetched
		elif self.pricing_mode == "Manual" and not getattr(self, "cost_currency", None):
			# default cost_currency to company_currency if blank
			if not self.company_currency:
				company = frappe.db.get_single_value("Global Defaults", "default_company")
				if company:
					self.company_currency = frappe.get_cached_value("Company", company, "default_currency")
			if self.company_currency and not getattr(self, "cost_currency", None):
				self.cost_currency = self.company_currency
				self.exchange_rate = 1

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
				if flt(self.estimated_base_rate):
					pass
		# compute preview tiers so form shows them after save even before Refresh
		try:
			if self.pricing_mode == "Manual":
				true_cost, tiers = recompute_manual_estimate(self)
				self.manual_true_cost = flt(true_cost, 2)
				self.basic_rate = flt(tiers.get("basic_rate") or 0, 2)
				self.target_rate = flt(tiers.get("target_rate") or 0, 2)
				self.rate_15 = flt(tiers.get("rate_15") or 0, 2)
				self.rate_30 = flt(tiers.get("rate_30") or 0, 2)
				self.rate_45 = flt(tiers.get("rate_45") or 0, 2)
				self.rate_commission = flt(tiers.get("rate_commission") or 0, 2)
				self.rate_commission_tax = flt(tiers.get("rate_commission_tax") or 0, 2)
				self.rate_target_commission = flt(tiers.get("rate_target_commission") or 0, 2)
				self.rate_target_commission_tax = flt(tiers.get("rate_target_commission_tax") or 0, 2)
				self.final_rate_per_unit = flt(tiers.get("final_rate_per_unit") or 0, 2)
				self.suggested_selling_price = flt(
					get_standard_rate(tiers, self.standard_selling_source_tier), 2
				)
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
		price_list = doc.price_list_30 or "Standard Selling"
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
				"basic_rate": flt(tiers.get("basic_rate") or 0, 2),
				"target_rate": flt(tiers.get("target_rate") or 0, 2),
				"rate_15": flt(tiers.get("rate_15") or 0, 2),
				"rate_30": flt(tiers.get("rate_30") or 0, 2),
				"rate_45": flt(tiers.get("rate_45") or 0, 2),
				"rate_commission": flt(tiers.get("rate_commission") or 0, 2),
				"rate_commission_tax": flt(tiers.get("rate_commission_tax") or 0, 2),
				"rate_target_commission": flt(tiers.get("rate_target_commission") or 0, 2),
				"rate_target_commission_tax": flt(tiers.get("rate_target_commission_tax") or 0, 2),
				"final_rate_per_unit": flt(tiers.get("final_rate_per_unit") or 0, 2),
				"suggested_selling_price": flt(standard_rate, 2),
				"current_selling_price": flt(current_sp, 2),
				"last_updated": now_datetime(),
			},
			update_modified=False,
		)
	else:
		recompute_suggested_price(doc.item_code)
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
	Apply tier rates to Item Price (all in Company Currency).
	- selected_tiers: list of keys like ["basic","15","30","45","commission","commission_tax","target","target_commission","target_commission_tax"] or None = all (6+conditionals)
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

	# collect tier → rate → price_list mapping (6 fixed + up to 3 conditional) — all Company Currency
	tier_defs = {
		"basic": (doc.basic_rate, doc.price_list_basic or "Selling - Basic"),
		"15": (doc.rate_15, doc.price_list_15 or "Selling - 15%"),
		"30": (doc.rate_30, doc.price_list_30 or "Selling - 30%"),
		"45": (doc.rate_45, doc.price_list_45 or "Selling - 45%"),
		"commission": (doc.rate_commission, doc.price_list_commission or "Selling - Commission"),
		"commission_tax": (
			doc.rate_commission_tax,
			doc.price_list_commission_tax or "Selling - Commission (Tax)",
		),
	}
	if flt(doc.target_margin_pct) and doc.price_list:
		tier_defs["target"] = (getattr(doc, "target_rate", 0), doc.price_list)
	if flt(doc.commission_pct) and getattr(doc, "price_list_target_commission", None):
		tier_defs["target_commission"] = (
			getattr(doc, "rate_target_commission", 0),
			getattr(doc, "price_list_target_commission", None) or "",
		)
	if flt(doc.wht_pct) and getattr(doc, "price_list_target_commission_tax", None):
		tier_defs["target_commission_tax"] = (
			getattr(doc, "rate_target_commission_tax", 0),
			getattr(doc, "price_list_target_commission_tax", None) or "",
		)

	# default to all available tiers if none selected
	if not selected_tiers:
		selected_tiers = list(tier_defs.keys())

	# standard selling override — ensure Standard Selling gets the chosen tier
	standard_map = {
		"Basic": doc.basic_rate,
		"15%": doc.rate_15,
		"30%": doc.rate_30,
		"45%": doc.rate_45,
		"Target": getattr(doc, "target_rate", 0),
		"Commission (10%)": doc.rate_commission,
		"Commission (Tax) (10%+3%)": doc.rate_commission_tax,
		"Commission": doc.rate_commission,
		"Commission (Tax)": doc.rate_commission_tax,
		"Target Commission": getattr(doc, "rate_target_commission", 0),
		"Target Commission (Tax)": getattr(doc, "rate_target_commission_tax", 0),
	}
	# fallback for Target blank → use rate_30
	if not flt(standard_map.get("Target")):
		standard_map["Target"] = doc.rate_30
	if not flt(standard_map.get("Target Commission")):
		standard_map["Target Commission"] = doc.rate_30
	if not flt(standard_map.get("Target Commission (Tax)")):
		standard_map["Target Commission (Tax)"] = doc.rate_30
	standard_rate = flt(standard_map.get(doc.standard_selling_source_tier or "30%"), 2)

	# validate selected tiers have price lists and are distinct (strict, include Standard Selling)
	for k in selected_tiers:
		if k not in tier_defs:
			continue
		_rate, pl = tier_defs[k]
		if not pl:
			label_map = {
				"target": "Price List — Target Margin",
				"target_commission": "Price List — Target Commission",
				"target_commission_tax": "Price List — Target Commission (Tax)",
			}
			lbl = label_map.get(k, k)
			frappe.throw(_("Price List for {0} is not set. Pick an existing Price List.").format(_(lbl)))
		if pl in FIXED_TIER_SET and k in ("target", "target_commission", "target_commission_tax"):
			frappe.throw(_("Price List {0} for {1} cannot be one of the 6 fixed tier lists.").format(pl, k))
	# strict duplicate check across selected tiers (blank ignored, Standard Selling included)
	seen_pl = {}
	for k in selected_tiers:
		if k not in tier_defs:
			continue
		_rate, pl = tier_defs[k]
		if not pl:
			continue
		if pl in seen_pl:
			frappe.throw(
				_("Price List {0} is used for both {1} and {2}. Please choose distinct Price Lists.").format(
					pl, seen_pl[pl], k
				)
			)
		seen_pl[pl] = k
	# also check Standard Selling duplicate if standard will be written
	standard_selling_pl = "Standard Selling"
	if standard_rate and standard_selling_pl in seen_pl:
		frappe.throw(
			_(
				"Price List {0} is used for both {1} and Standard Selling. Please choose distinct Price Lists."
			).format(standard_selling_pl, seen_pl[standard_selling_pl])
		)

	# validate tiers have values
	any_rate = False
	for k in selected_tiers:
		if k in tier_defs and flt(tier_defs[k][0]):
			any_rate = True
	if not any_rate and not standard_rate:
		frappe.throw("No tier rates computed. Click Recalculate before applying.")

	# All price lists must be Company Currency
	company_ccy = doc.company_currency or frappe.get_cached_value(
		"Company",
		frappe.db.get_single_value("Global Defaults", "default_company"),
		"default_currency",
	)
	for k in selected_tiers:
		if k not in tier_defs:
			continue
		_rate, pl = tier_defs[k]
		if not pl:
			continue
		ccy = frappe.get_cached_value("Price List", pl, "currency")
		if ccy and company_ccy and ccy != company_ccy:
			frappe.throw(
				_("Price List {0} for tier {1} currency {2} must be Company Currency {3}.").format(
					pl, k, ccy, company_ccy
				)
			)

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
	standard_selling_pl = "Standard Selling"
	if standard_rate and standard_selling_pl not in [pl for _, pl in tiers_to_write.values()]:
		# check if any tier already writes to Standard Selling with same rate — avoid duplicate write if same
		already_standard = any(
			pl == standard_selling_pl and flt(rate, 2) == flt(standard_rate, 2)
			for rate, pl in tiers_to_write.values()
		)
		if not already_standard:
			tiers_to_write["_standard"] = (flt(standard_rate, 2), standard_selling_pl)

	applied = []
	for _tier_key, (rate, price_list) in tiers_to_write.items():
		currency = frappe.get_cached_value("Price List", price_list, "currency") or company_ccy
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
