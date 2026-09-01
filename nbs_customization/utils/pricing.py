import frappe
from frappe.utils import flt, now_datetime


# ── Pure tier calculator (PDF formulas, margin is % of selling price) ──────────

STANDARD_TIER_MAP = {
	"Basic": "basic_rate",
	"15%": "rate_15",
	"30%": "rate_30",
	"45%": "rate_45",
	"Commission": "rate_commission",
	"Commission (Tax)": "rate_commission_tax",
}


def compute_tiers(true_cost, target_margin_pct=0, commission_pct=10, wht_pct=3):
	"""
	Compute all 6 tier rates from true_cost (per unit, in quote currency).

	- basic = true_cost
	- rate_X = true_cost / (1 - margin_X/100)
	- commission tier = rate_target / (1 - commission/100)  (if commission>0)
	- commission_tax tier = commission_tier / (1 - wht/100)  (if wht>0)
	- final = commission_tax tier (target + commission + wHT)

	Margins are % of selling price, not markup — matches PDF: SP = Cost / (1 - Margin%)
	"""
	true_cost = flt(true_cost, 2)
	target_margin_pct = flt(target_margin_pct)
	commission_pct = flt(commission_pct)
	wht_pct = flt(wht_pct)

	def _rate(cost, pct):
		pct = flt(pct)
		if pct <= 0:
			return flt(cost, 2)
		if pct >= 100:
			return 0
		return flt(cost / (1 - pct / 100), 2)

	basic = _rate(true_cost, 0)
	r15 = _rate(true_cost, 15)
	r30 = _rate(true_cost, 30)
	r45 = _rate(true_cost, 45)
	# target margin tier (used as primary for this item)
	r_target = _rate(true_cost, target_margin_pct)

	# commission applied on top of target margin tier
	if commission_pct > 0 and commission_pct < 100 and r_target:
		r_commission = flt(r_target / (1 - commission_pct / 100), 2)
	else:
		r_commission = flt(r_target, 2)

	# WHT applied on top of commission tier
	if wht_pct > 0 and wht_pct < 100 and r_commission:
		r_commission_tax = flt(r_commission / (1 - wht_pct / 100), 2)
	else:
		r_commission_tax = flt(r_commission, 2)

	return {
		"basic_rate": basic,
		"rate_15": r15,
		"rate_30": r30,
		"rate_45": r45,
		"rate_commission": r_commission,
		"rate_commission_tax": r_commission_tax,
		"final_rate_per_unit": r_commission_tax,
		"rate_target": r_target,
	}


def get_standard_rate(tiers, source_tier):
	"""Map standard_selling_source_tier Select value to the correct tier rate."""
	key = STANDARD_TIER_MAP.get(source_tier or "30%")
	if key and key in tiers:
		return flt(tiers[key], 2)
	# fallback to rate_30
	return flt(tiers.get("rate_30"), 2)


# ── FX helpers ──────────────────────────────────────────────────────────────────


def get_exchange_rate(from_currency, to_currency, date=None):
	"""Fetch exchange rate from Currency Exchange for date (<=date, desc). Manual override if 0."""
	if not from_currency or not to_currency or from_currency == to_currency:
		return 1.0
	if not date:
		date = frappe.utils.today()
	rate = frappe.db.get_value(
		"Currency Exchange",
		{"from_currency": from_currency, "to_currency": to_currency, "date": ["<=", date]},
		"exchange_rate",
		order_by="date desc",
	)
	return flt(rate) or 0


# ── Allocation helper for batch (value-weight, PDF p2-4) ───────────────────────


def allocate_shared_costs(batch_doc):
	"""
	Distribute header shared costs across child rows by value weight:
	  weight_i = base_total_i / sum(base_total)
	  allocated_*_i = total_* * weight_i

	Mutates batch_doc.items in place, also computes true_cost + tiers per row.
	"""
	items = batch_doc.items or []
	if not items:
		return

	# compute base_total per row first
	for row in items:
		row.base_total = flt(flt(row.qty) * flt(row.unit_cost), 2)

	total_base = sum(flt(r.base_total) for r in items)
	if not total_base:
		return

	# collect header totals (in quote currency)
	t_bank = flt(batch_doc.total_bank_charges)
	t_freight = flt(batch_doc.total_freight)
	t_clearing = flt(batch_doc.total_clearing_fees)
	t_tin = flt(batch_doc.total_transport_in)
	t_tout = flt(batch_doc.total_transport_out)
	t_over = flt(batch_doc.total_overhead)
	t_fixed = flt(batch_doc.total_fixed_cost)

	# last-row delta correction to fix rounding
	n = len(items)
	cum = {"bank": 0, "freight": 0, "clearing": 0, "tin": 0, "tout": 0, "over": 0, "fixed": 0}

	for idx, row in enumerate(items):
		is_last = idx == n - 1
		weight = flt(row.base_total) / total_base if total_base else 0

		if is_last:
			row.allocated_bank_charges = flt(t_bank - cum["bank"], 2)
			row.allocated_freight = flt(t_freight - cum["freight"], 2)
			row.allocated_clearing_fees = flt(t_clearing - cum["clearing"], 2)
			row.allocated_transport_in = flt(t_tin - cum["tin"], 2)
			row.allocated_transport_out = flt(t_tout - cum["tout"], 2)
			row.allocated_overhead = flt(t_over - cum["over"], 2)
			row.allocated_fixed_cost = flt(t_fixed - cum["fixed"], 2)
		else:
			row.allocated_bank_charges = flt(t_bank * weight, 2)
			row.allocated_freight = flt(t_freight * weight, 2)
			row.allocated_clearing_fees = flt(t_clearing * weight, 2)
			row.allocated_transport_in = flt(t_tin * weight, 2)
			row.allocated_transport_out = flt(t_tout * weight, 2)
			row.allocated_overhead = flt(t_over * weight, 2)
			row.allocated_fixed_cost = flt(t_fixed * weight, 2)
			cum["bank"] += row.allocated_bank_charges
			cum["freight"] += row.allocated_freight
			cum["clearing"] += row.allocated_clearing_fees
			cum["tin"] += row.allocated_transport_in
			cum["tout"] += row.allocated_transport_out
			cum["over"] += row.allocated_overhead
			cum["fixed"] += row.allocated_fixed_cost

		allocated_sum = (
			flt(row.allocated_bank_charges)
			+ flt(row.allocated_freight)
			+ flt(row.allocated_clearing_fees)
			+ flt(row.allocated_transport_in)
			+ flt(row.allocated_transport_out)
			+ flt(row.allocated_overhead)
			+ flt(row.allocated_fixed_cost)
		)
		row.true_cost = flt(flt(row.base_total) + allocated_sum, 2)
		row.true_cost_per_unit = flt(row.true_cost / flt(row.qty), 2) if flt(row.qty) else flt(row.true_cost, 2)

		tiers = compute_tiers(
			row.true_cost_per_unit,
			target_margin_pct=row.target_margin_pct,
			commission_pct=batch_doc.commission_pct,
			wht_pct=batch_doc.wht_pct,
		)
		row.basic_rate = tiers["basic_rate"]
		row.rate_15 = tiers["rate_15"]
		row.rate_30 = tiers["rate_30"]
		row.rate_45 = tiers["rate_45"]
		row.rate_commission = tiers["rate_commission"]
		row.rate_commission_tax = tiers["rate_commission_tax"]
		row.final_rate_per_unit = tiers["final_rate_per_unit"]
		row.final_total = flt(flt(row.final_rate_per_unit) * flt(row.qty), 2)

		# dual currency preview if FX applicable
		if batch_doc.quote_currency and batch_doc.company_currency and batch_doc.quote_currency != batch_doc.company_currency:
			rate = flt(batch_doc.exchange_rate) or get_exchange_rate(
				batch_doc.quote_currency, batch_doc.company_currency, batch_doc.exchange_rate_date
			)
			if rate:
				row.final_rate_per_unit_company_currency = flt(row.final_rate_per_unit * rate, 2)


def recompute_manual_estimate(doc):
	"""Compute tiers for a single Manual-mode Item Pricing Settings doc."""
	if flt(doc.estimated_true_cost_override):
		true_cost = flt(doc.estimated_true_cost_override, 2)
	else:
		true_cost = flt(
			flt(doc.estimated_base_rate)
			+ flt(doc.manual_bank_charges)
			+ flt(doc.manual_freight)
			+ flt(doc.manual_clearing_fees)
			+ flt(doc.manual_transport_in)
			+ flt(doc.manual_transport_out)
			+ flt(doc.manual_overhead)
			+ flt(doc.manual_fixed_cost),
			2,
		)
	tiers = compute_tiers(
		true_cost,
		target_margin_pct=doc.target_margin_pct,
		commission_pct=doc.commission_pct,
		wht_pct=doc.wht_pct,
	)
	return true_cost, tiers


def _tier_values_for_settings(doc, true_cost, tiers):
	"""Build the db.set_value dict for tier fields + standard selling mapping."""
	standard_rate = get_standard_rate(tiers, doc.standard_selling_source_tier)
	values = {
		"manual_true_cost": flt(true_cost, 2) if doc.pricing_mode == "Manual" else 0,
		"current_valuation_rate": flt(true_cost, 4) if doc.pricing_mode == "Auto" else flt(doc.current_valuation_rate, 4),
		"basic_rate": tiers["basic_rate"],
		"rate_15": tiers["rate_15"],
		"rate_30": tiers["rate_30"],
		"rate_45": tiers["rate_45"],
		"rate_commission": tiers["rate_commission"],
		"rate_commission_tax": tiers["rate_commission_tax"],
		"final_rate_per_unit": tiers["final_rate_per_unit"],
		"suggested_selling_price": standard_rate,
		"last_updated": now_datetime(),
	}
	# keep legacy price_list in sync with price_list_30 (Standard Selling)
	if doc.price_list_30:
		values["price_list"] = doc.price_list_30
	return values


# ── Auto recompute (SLE valuation) ─────────────────────────────────────────────


def recompute_suggested_price(item_code):
	"""
	Reads the current valuation rate for item_code from the most recent
	Stock Ledger Entry, then updates the Item Pricing Settings record with:
	  - current_valuation_rate
	  - all 6 tier rates
	  - suggested_selling_price (standard_rate via standard_selling_source_tier, default 30%)
	  - current_selling_price  (what is currently live in Item Price for Standard Selling)
	  - last_updated

	Does NOT write to Item Price. That is a deliberate manual step
	performed by the pricing manager via the Apply button on the form.

	Silently skips if no Item Pricing Settings record exists for the item,
	so this function will never block a Purchase Receipt or LCV submission.
	"""
	settings_name = frappe.db.get_value("Item Pricing Settings", {"item_code": item_code}, "name")
	if not settings_name:
		return

	settings = frappe.db.get_value(
		"Item Pricing Settings",
		settings_name,
		[
			"target_margin_pct",
			"commission_pct",
			"wht_pct",
			"standard_selling_source_tier",
			"pricing_mode",
			"price_list",
			"price_list_30",
		],
		as_dict=True,
	)

	# Only Auto mode is driven by SLE; Manual is quotation-based
	if settings.pricing_mode == "Manual":
		return

	margin_pct = flt(settings.target_margin_pct)
	if not margin_pct or margin_pct <= 0 or margin_pct >= 100:
		return

	val_rate = _get_current_valuation_rate(item_code)
	if not val_rate:
		return

	tiers = compute_tiers(
		flt(val_rate, 4),
		target_margin_pct=margin_pct,
		commission_pct=flt(settings.commission_pct) or 10,
		wht_pct=flt(settings.wht_pct) or 3,
	)
	standard_rate = get_standard_rate(tiers, settings.standard_selling_source_tier)

	# Standard Selling is the live price (price_list_30 → Standard Selling reuse)
	price_list = settings.price_list_30 or settings.price_list or "Standard Selling"
	current_sp = flt(
		frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "price_list": price_list, "selling": 1},
			"price_list_rate",
		)
	)

	frappe.db.set_value(
		"Item Pricing Settings",
		settings_name,
		{
			"current_valuation_rate": flt(val_rate, 4),
			"basic_rate": tiers["basic_rate"],
			"rate_15": tiers["rate_15"],
			"rate_30": tiers["rate_30"],
			"rate_45": tiers["rate_45"],
			"rate_commission": tiers["rate_commission"],
			"rate_commission_tax": tiers["rate_commission_tax"],
			"final_rate_per_unit": tiers["final_rate_per_unit"],
			"suggested_selling_price": flt(standard_rate, 2),
			"current_selling_price": flt(current_sp, 2),
			"last_updated": now_datetime(),
		},
		update_modified=False,
	)


def _get_current_valuation_rate(item_code):
	"""
	Returns the valuation rate from the most recent inbound Stock Ledger
	Entry for the item. This is ERPNext's own computed rate — moving average
	or FIFO — after the latest receipt or LCV adjustment. Reading from SLE
	is more reliable than reading from Bin because Bin aggregates across
	warehouses and can lag briefly after an LCV submission.
	"""
	result = frappe.db.get_value(
		"Stock Ledger Entry",
		{
			"item_code": item_code,
			"is_cancelled": 0,
			"actual_qty": [">", 0],
		},
		"valuation_rate",
		order_by="posting_date desc, posting_time desc, creation desc",
	)
	return flt(result)


def on_purchase_receipt_submit(doc, method=None):
	"""
	doc_events trigger — fires when a Purchase Receipt is submitted.
	Recomputes suggested prices for every item on the receipt.
	Each item is wrapped in its own try/except so one bad item
	never blocks the others or the receipt itself.
	"""
	item_codes = list({row.item_code for row in doc.items})
	for item_code in item_codes:
		try:
			recompute_suggested_price(item_code)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Pricing recompute failed: {item_code} (PR: {doc.name})",
			)


def on_landed_cost_voucher_submit(doc, method=None):
	"""
	doc_events trigger — fires when a Landed Cost Voucher is submitted.
	LCV submission is exactly the moment the valuation rate settles to its
	final value, so this is the most important trigger of the two.
	"""
	item_codes = list({row.item_code for row in doc.items})
	for item_code in item_codes:
		try:
			recompute_suggested_price(item_code)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Pricing recompute failed: {item_code} (LCV: {doc.name})",
			)
