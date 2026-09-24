# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from nbs_customization.utils.pricing import FIXED_TIER_SET, allocate_shared_costs, get_exchange_rate


class ItemPricingQuotationBatch(Document):
	def validate(self):
		self._set_company_currency_and_rate()
		self._ensure_fixed_tier_lists()
		self._validate_target_pairs()
		self._validate_source_tier()
		self._validate_cost_conversion()
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

	def _set_company_currency_and_rate(self):
		if not self.company:
			return
		if not self.company_currency:
			self.company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		if not self.exchange_rate_date:
			self.exchange_rate_date = self.posting_date or today()
		# Legacy: copy old quote_currency → cost_currency if blank
		if not getattr(self, "cost_currency", None) and self.name:
			try:
				res = frappe.db.sql(
					"SELECT `quote_currency` FROM `tabItem Pricing Quotation Batch` WHERE name=%s",
					(self.name,),
				)
				if res and res[0] and res[0][0]:
					self.cost_currency = res[0][0]
			except Exception:
				pass
		# cost_currency → company
		cost_ccy = getattr(self, "cost_currency", None)
		company_ccy = getattr(self, "company_currency", None)
		if not cost_ccy and company_ccy:
			self.cost_currency = company_ccy
			self.exchange_rate = 1
			return
		if cost_ccy and company_ccy:
			if cost_ccy == company_ccy:
				self.exchange_rate = 1
			elif not flt(self.exchange_rate):
				fetched = get_exchange_rate(cost_ccy, company_ccy, self.exchange_rate_date)
				if fetched:
					self.exchange_rate = fetched

	def _validate_target_pairs(self):
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
		# header price_list_target optional — if set must not be fixed set and any row target check will enforce

		if self.price_list_target and self.price_list_target in FIXED_TIER_SET:
			frappe.throw(
				_("Price List — Target Margin cannot be one of the 6 fixed tier lists: {0}").format(
					self.price_list_target
				)
			)

	def _validate_source_tier(self):
		source = self.standard_selling_source_tier or "30%"
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
		# Target source for batch depends on rows — at least one row must have target if source is Target
		if source == "Target":
			if not any(flt(r.target_margin_pct) for r in (self.items or [])):
				# allow if batch will have no target yet? defer to per-row validation at apply — but warn at validate
				pass

	def _validate_cost_conversion(self):
		cost_ccy = getattr(self, "cost_currency", None)
		company_ccy = getattr(self, "company_currency", None)
		if cost_ccy and company_ccy and cost_ccy != company_ccy:
			if not flt(self.exchange_rate):
				frappe.throw(
					_("Exchange Rate (Cost → Company) is required when Cost Currency != Company Currency.")
				)
		else:
			# same currency: ensure convert flags off and rate 1
			if flt(self.exchange_rate) != 1 and cost_ccy and company_ccy and cost_ccy == company_ccy:
				self.exchange_rate = 1

	def _validate_no_duplicate_price_lists(self):
		# header optional lists distinct
		header_lists = [
			("Price List — Target Margin", self.price_list_target),
			("Price List — Target Commission", self.price_list_target_commission),
			("Price List — Target Commission (Tax)", self.price_list_target_commission_tax),
		]
		seen = {}
		for label, name in header_lists:
			if not name:
				continue
			if name in seen:
				frappe.throw(
					_(
						"Price List {0} is used for both {1} and {2}. Please choose distinct Price Lists."
					).format(name, seen[name], label)
				)
			seen[name] = label
		# per-row effective duplicate check
		for row in self.items or []:
			eff_target = getattr(row, "price_list_target", None) or self.price_list_target or ""
			eff_tc = (
				getattr(row, "price_list_target_commission", None) or self.price_list_target_commission or ""
			)
			eff_tct = (
				getattr(row, "price_list_target_commission_tax", None)
				or self.price_list_target_commission_tax
				or ""
			)
			row_lists = [
				("Price List — Target Margin (row)", eff_target),
				("Price List — Target Commission (row)", eff_tc),
				("Price List — Target Commission (Tax) (row)", eff_tct),
			]
			# check row overrides duplicate with header optional lists (already) and check not in fixed set
			for rlabel, rname in row_lists:
				if not rname:
					continue
				if rname in FIXED_TIER_SET:
					frappe.throw(
						_("Row {0} ({1}): Price List {2} cannot be one of the 6 fixed tier lists.").format(
							row.idx or row.item_code, rlabel, rname
						)
					)
				for _hlabel, hname in header_lists:
					if hname and rname == hname and rlabel.startswith("Price List — Target Margin"):
						# same effective as header — not duplicate, just fallback; skip
						continue
				# duplicate among row's own lists
				# (simple: eff lists distinct)
			if eff_target and eff_tc and eff_target == eff_tc:
				frappe.throw(
					_("Row {0}: Price List — Target Margin and Target Commission cannot be the same.").format(
						row.idx or row.item_code
					)
				)
			if eff_target and eff_tct and eff_target == eff_tct:
				frappe.throw(
					_(
						"Row {0}: Price List — Target Margin and Target Commission (Tax) cannot be the same."
					).format(row.idx or row.item_code)
				)
			if eff_tc and eff_tct and eff_tc == eff_tct:
				frappe.throw(
					_(
						"Row {0}: Price List — Target Commission and Target Commission (Tax) cannot be the same."
					).format(row.idx or row.item_code)
				)

	def _validate_items(self):
		self._validate_no_duplicate_price_lists()
		if not self.items:
			return
		for row in self.items:
			if not row.item_code:
				frappe.throw("Item Code is required in every row.")
			if flt(row.qty) <= 0:
				frappe.throw(f"Qty must be > 0 for {row.item_code}.")
			margin = flt(row.target_margin_pct)
			if margin:
				if margin >= 100:
					frappe.throw(f"Target Margin must be less than 100% for {row.item_code}.")
				if margin < 1:
					frappe.throw(f"Target Margin must be blank or 1-99% for {row.item_code}.")
				eff_pl = getattr(row, "price_list_target", None) or self.price_list_target
				if not eff_pl:
					frappe.throw(
						f"Price List — Target Margin is required for {row.item_code} when Target Margin % is set."
					)
			else:
				# if row has price_list_target but no margin → error
				if getattr(row, "price_list_target", None):
					frappe.throw(
						f"Target Margin % is required for {row.item_code} when Price List — Target is set."
					)
			# row-level commission/wht are header-driven — no per-row commission field, so nothing to validate here
		# validate all price lists are company currency
		company_ccy = self.company_currency
		if company_ccy:
			for pl in [
				self.price_list_basic,
				self.price_list_15,
				self.price_list_30,
				self.price_list_45,
				self.price_list_commission,
				self.price_list_commission_tax,
				self.price_list_target,
				self.price_list_target_commission,
				self.price_list_target_commission_tax,
			]:
				if pl:
					ccy = frappe.get_cached_value("Price List", pl, "currency")
					if ccy and ccy != company_ccy:
						frappe.throw(
							_("Price List {0} currency {1} must be Company Currency {2}.").format(
								pl, ccy, company_ccy
							)
						)

	def _compute_totals(self):
		self.total_base = flt(sum(flt(r.base_total) for r in self.items), 2)
		self.total_true_cost = flt(sum(flt(r.true_cost) for r in self.items), 2)
		self.total_final = flt(sum(flt(r.final_total) for r in self.items), 2)


def _ensure_pricing_settings_for_batch_row(batch, row):
	"""
	Create or update Item Pricing Settings (Manual) for row.item_code,
	then bulk-apply tier Item Price rows (all Company Currency).
	Cost conversion per-field handled in allocate_shared_costs / recompute_manual_estimate.
	"""
	existing = frappe.db.get_value("Item Pricing Settings", {"item_code": row.item_code}, "name")
	uom = frappe.get_cached_value("Item", row.item_code, "sales_uom") or frappe.get_cached_value(
		"Item", row.item_code, "stock_uom"
	)

	# map tiers from row (6 fixed + optional targets) — all in company currency
	tiers = {
		"basic_rate": row.basic_rate,
		"target_rate": getattr(row, "target_rate", 0),
		"rate_15": row.rate_15,
		"rate_30": row.rate_30,
		"rate_45": row.rate_45,
		"rate_commission": row.rate_commission,
		"rate_commission_tax": row.rate_commission_tax,
		"rate_target_commission": getattr(row, "rate_target_commission", 0),
		"rate_target_commission_tax": getattr(row, "rate_target_commission_tax", 0),
		"final_rate_per_unit": row.final_rate_per_unit,
	}

	# standard rate for Standard Selling = source tier (batch-level, includes Target)
	source_map = {
		"Basic": row.basic_rate,
		"15%": row.rate_15,
		"30%": row.rate_30,
		"45%": row.rate_45,
		"Target": getattr(row, "target_rate", 0) or row.rate_30,
		"Commission (10%)": row.rate_commission,
		"Commission (Tax) (10%+3%)": row.rate_commission_tax,
		# backward compat for old docs still storing Commission without suffix
		"Commission": row.rate_commission,
		"Commission (Tax)": row.rate_commission_tax,
		"Target Commission": getattr(row, "rate_target_commission", 0) or row.rate_30,
		"Target Commission (Tax)": getattr(row, "rate_target_commission_tax", 0) or row.rate_30,
	}
	standard_rate = flt(source_map.get(batch.standard_selling_source_tier or "30%"), 2) or flt(row.rate_30, 2)

	if existing:
		doc = frappe.get_doc("Item Pricing Settings", existing)
		doc.pricing_mode = "Manual"
		doc.target_margin_pct = row.target_margin_pct
		doc.commission_pct = batch.commission_pct
		doc.wht_pct = batch.wht_pct
		doc.standard_selling_source_tier = batch.standard_selling_source_tier
		doc.cost_currency = getattr(batch, "cost_currency", None) or batch.company_currency
		doc.company_currency = batch.company_currency
		doc.exchange_rate = batch.exchange_rate
		doc.exchange_rate_date = batch.exchange_rate_date
		doc.estimated_base_rate = row.unit_cost
		doc.manual_qty = row.qty
		doc.manual_true_cost = row.true_cost_per_unit
		doc.basic_rate = tiers["basic_rate"]
		doc.target_rate = tiers["target_rate"]
		doc.rate_15 = tiers["rate_15"]
		doc.rate_30 = tiers["rate_30"]
		doc.rate_45 = tiers["rate_45"]
		doc.rate_commission = tiers["rate_commission"]
		doc.rate_commission_tax = tiers["rate_commission_tax"]
		doc.rate_target_commission = tiers["rate_target_commission"]
		doc.rate_target_commission_tax = tiers["rate_target_commission_tax"]
		doc.final_rate_per_unit = tiers["final_rate_per_unit"]
		doc.suggested_selling_price = standard_rate
		# Only propagate target price list when row has target margin (per Q4 row autonomy)
		if flt(row.target_margin_pct):
			doc.price_list = (
				getattr(row, "price_list_target", None) or getattr(batch, "price_list_target", None) or ""
			)
		else:
			doc.price_list = ""
		doc.price_list_target_commission = (
			(
				getattr(row, "price_list_target_commission", None)
				or getattr(batch, "price_list_target_commission", None)
				or ""
			)
			if flt(batch.commission_pct)
			else ""
		)
		doc.price_list_target_commission_tax = (
			(
				getattr(row, "price_list_target_commission_tax", None)
				or getattr(batch, "price_list_target_commission_tax", None)
				or ""
			)
			if flt(batch.wht_pct)
			else ""
		)
		doc.price_list_basic = batch.price_list_basic
		doc.price_list_15 = batch.price_list_15
		doc.price_list_30 = batch.price_list_30
		doc.price_list_45 = batch.price_list_45
		doc.price_list_commission = batch.price_list_commission
		doc.price_list_commission_tax = batch.price_list_commission_tax
		doc.reference_quotation_batch = batch.name
		# carry convert flags for audit? Not needed — costs already converted to company in tiers
		doc.flags.ignore_permissions = True
		doc.save()
	else:
		# Determine target price lists conditionally (row target only, commission/wht batch-level)
		_target_pl = (
			(getattr(row, "price_list_target", None) or getattr(batch, "price_list_target", None) or "")
			if flt(row.target_margin_pct)
			else ""
		)
		_target_comm_pl = (
			(
				getattr(row, "price_list_target_commission", None)
				or getattr(batch, "price_list_target_commission", None)
				or ""
			)
			if flt(batch.commission_pct)
			else ""
		)
		_target_comm_tax_pl = (
			(
				getattr(row, "price_list_target_commission_tax", None)
				or getattr(batch, "price_list_target_commission_tax", None)
				or ""
			)
			if flt(batch.wht_pct)
			else ""
		)
		doc = frappe.get_doc(
			{
				"doctype": "Item Pricing Settings",
				"item_code": row.item_code,
				"pricing_mode": "Manual",
				"target_margin_pct": row.target_margin_pct,
				"commission_pct": batch.commission_pct,
				"wht_pct": batch.wht_pct,
				"standard_selling_source_tier": batch.standard_selling_source_tier,
				"cost_currency": getattr(batch, "cost_currency", None) or batch.company_currency,
				"company_currency": batch.company_currency,
				"exchange_rate": batch.exchange_rate,
				"exchange_rate_date": batch.exchange_rate_date,
				"estimated_base_rate": row.unit_cost,
				"manual_qty": row.qty,
				"manual_true_cost": row.true_cost_per_unit,
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
				"suggested_selling_price": standard_rate,
				"price_list": _target_pl,
				"price_list_target_commission": _target_comm_pl,
				"price_list_target_commission_tax": _target_comm_tax_pl,
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

	# now write Item Price tiers (all Company Currency)
	_apply_tiers_from_batch(batch, row, doc, uom, standard_rate)


def _apply_tiers_from_batch(batch, row, settings_doc, uom, standard_rate):
	"""Bulk upsert Item Price per tier (6 fixed + optional targets) — all Company Currency."""
	target_pl = getattr(row, "price_list_target", None) or getattr(batch, "price_list_target", None) or ""
	target_commission_pl = (
		getattr(row, "price_list_target_commission", None)
		or getattr(batch, "price_list_target_commission", None)
		or ""
	)
	target_commission_tax_pl = (
		getattr(row, "price_list_target_commission_tax", None)
		or getattr(batch, "price_list_target_commission_tax", None)
		or ""
	)
	tier_price_lists = {
		"basic": (row.basic_rate, batch.price_list_basic),
		"15": (row.rate_15, batch.price_list_15),
		"30": (row.rate_30, batch.price_list_30),
		"45": (row.rate_45, batch.price_list_45),
		"commission": (row.rate_commission, batch.price_list_commission),
		"commission_tax": (row.rate_commission_tax, batch.price_list_commission_tax),
	}
	# Target tier: skip if it would duplicate Standard Selling (standard selling handles it)
	if flt(row.target_rate) and target_pl:
		if target_pl == "Standard Selling":
			# Let Standard Selling write handle target rate when source is Target; do not create duplicate tier
			# Only add if source tier is not Target to avoid duplicate error
			if batch.standard_selling_source_tier != "Target":
				frappe.throw(
					_(
						"Row {0}: Price List — Target Margin cannot be Standard Selling when Standard Selling source is not Target. Use a distinct target price list."
					).format(row.item_code)
				)
			# else: skip adding target tier — standard_rate already equals target_rate
		else:
			tier_price_lists["target"] = (getattr(row, "target_rate", 0), target_pl)
	elif flt(getattr(row, "target_rate", 0)) and not target_pl:
		frappe.throw(_("Row {0}: Price List for Target Margin is not set.").format(row.item_code))
	if flt(getattr(row, "rate_target_commission", 0)) and target_commission_pl:
		tier_price_lists["target_commission"] = (
			getattr(row, "rate_target_commission", 0),
			target_commission_pl,
		)
	elif flt(getattr(row, "rate_target_commission", 0)) and not target_commission_pl:
		frappe.throw(_("Row {0}: Price List for Target Commission is not set.").format(row.item_code))
	if flt(getattr(row, "rate_target_commission_tax", 0)) and target_commission_tax_pl:
		tier_price_lists["target_commission_tax"] = (
			getattr(row, "rate_target_commission_tax", 0),
			target_commission_tax_pl,
		)
	elif flt(getattr(row, "rate_target_commission_tax", 0)) and not target_commission_tax_pl:
		frappe.throw(_("Row {0}: Price List for Target Commission (Tax) is not set.").format(row.item_code))

	# duplicate & not-in-fixed-set
	seen = {}
	for _k, (_r, _pl) in tier_price_lists.items():
		if not _pl:
			continue
		if _pl in seen:
			frappe.throw(
				_("Price List {0} is used for both {1} and {2}. Please choose distinct Price Lists.").format(
					_pl, seen[_pl], _k
				)
			)
		seen[_pl] = _k
	if flt(standard_rate) and "Standard Selling" in seen:
		frappe.throw(
			_(
				"Price List {0} is used for both {1} and Standard Selling. Please choose distinct Price Lists."
			).format("Standard Selling", seen["Standard Selling"])
		)
	# All price lists must be Company Currency
	company_ccy = batch.company_currency
	if company_ccy:
		for _k, (_r, _pl) in tier_price_lists.items():
			if not _pl:
				continue
			ccy = frappe.get_cached_value("Price List", _pl, "currency")
			if ccy and ccy != company_ccy:
				frappe.throw(
					_("Price List {0} for tier {1} currency {2} must be Company Currency {3}.").format(
						_pl, _k, ccy, company_ccy
					)
				)

	for _tier_key, (rate, pl) in tier_price_lists.items():
		if not pl or not flt(rate):
			continue
		currency = frappe.get_cached_value("Price List", pl, "currency") or company_ccy
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

	# Ensure Standard Selling (separate from Selling - 30%) reflects source tier — all Company Currency
	if flt(standard_rate):
		std_currency = frappe.get_cached_value("Price List", "Standard Selling", "currency") or company_ccy
		std_existing = frappe.db.get_value(
			"Item Price", {"item_code": row.item_code, "price_list": "Standard Selling", "selling": 1}, "name"
		)
		if std_existing:
			frappe.db.set_value(
				"Item Price",
				std_existing,
				{"price_list_rate": flt(standard_rate, 2), "currency": std_currency, "valid_from": today()},
				update_modified=True,
			)
		else:
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": row.item_code,
					"price_list": "Standard Selling",
					"price_list_rate": flt(standard_rate, 2),
					"currency": std_currency,
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
