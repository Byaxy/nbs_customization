import frappe
from frappe.utils import flt, now_datetime

# ── Pure tier calculator (PDF formulas, margin is % of selling price) ──────────

STANDARD_TIER_MAP = {
	"Basic": "basic_rate",
	"15%": "rate_15",
	"30%": "rate_30",
	"45%": "rate_45",
	"Target": "target_rate",
	"Commission": "rate_commission",
	"Commission (Tax)": "rate_commission_tax",
	"Target Commission": "rate_target_commission",
	"Target Commission (Tax)": "rate_target_commission_tax",
}

FIXED_TIER_SET = {
	"Selling - Basic",
	"Selling - 15%",
	"Selling - 30%",
	"Selling - 45%",
	"Selling - Commission",
	"Selling - Commission (Tax)",
}


def compute_tiers(true_cost, target_margin_pct=None, commission_pct=None, wht_pct=None):
	"""
	Compute all tier rates from true_cost (per unit, in company currency).

	- basic = true_cost
	- rate_X = true_cost / (1 - margin_X/100) for X in 15/30/45
	- target = true_cost / (1 - target_margin/100)  (fallback 30% when blank)
	- fixed commission 10%  = target(+fallback) / (1 - 0.10)
	- fixed commission+tax 10+3% = fixed_commission / (1 - 0.03)
	- target commission (variable c%) = target / (1 - commission_pct/100)  (only if c% set)
	- target commission+tax (variable c%+w%) = target_commission / (1 - wht_pct/100)  (only if w% set)
	- final = target_commission_tax or target_commission or commission_tax

	Margins are % of selling price, not markup — matches PDF: SP = Cost / (1 - Margin%)
	All true_cost inputs must be in company currency (converted per-field if needed).
	"""
	true_cost = flt(true_cost, 2)
	target_pct = flt(target_margin_pct) if flt(target_margin_pct) else None
	commission_pct = flt(commission_pct) if flt(commission_pct) else None
	wht_pct = flt(wht_pct) if flt(wht_pct) else None

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
	# target fallback 30% when blank (Q2)
	if target_pct and 0 < target_pct < 100:
		r_target = _rate(true_cost, target_pct)
		r_target_raw = r_target
	else:
		r_target = r30
		r_target_raw = None

	# fixed commission 10% and fixed commission+tax 10%+3% — always from r_target (fallback-included)
	r_commission = flt(r_target / (1 - 0.10), 2) if r_target else flt(r_target, 2)
	r_commission_tax = flt(r_commission / (1 - 0.03), 2) if r_commission else flt(r_commission, 2)

	# variable target commission / target commission+tax — only if % set
	r_target_commission = None
	r_target_commission_tax = None
	if commission_pct and 0 < commission_pct < 100 and r_target:
		r_target_commission = flt(r_target / (1 - commission_pct / 100), 2)
	if wht_pct and 0 < wht_pct < 100 and r_target_commission:
		r_target_commission_tax = flt(r_target_commission / (1 - wht_pct / 100), 2)

	final = r_target_commission_tax or r_target_commission or r_commission_tax

	return {
		"basic_rate": flt(basic, 2),
		"target_rate": flt(r_target_raw or 0, 2),
		"rate_15": flt(r15, 2),
		"rate_30": flt(r30, 2),
		"rate_45": flt(r45, 2),
		"rate_commission": flt(r_commission, 2),
		"rate_commission_tax": flt(r_commission_tax, 2),
		"rate_target_commission": flt(r_target_commission or 0, 2),
		"rate_target_commission_tax": flt(r_target_commission_tax or 0, 2),
		"final_rate_per_unit": flt(final, 2),
		"rate_target": flt(r_target_raw or 0, 2),
	}


def get_standard_rate(tiers, source_tier):
	"""Map standard_selling_source_tier Select value to the correct tier rate."""
	key = STANDARD_TIER_MAP.get(source_tier or "30%")
	if key and key in tiers:
		val = tiers[key]
		if val is not None:
			return flt(val, 2)
	# fallback to rate_30
	return flt(tiers.get("rate_30"), 2)


# ── FX helpers ──────────────────────────────────────────────────────────────────


@frappe.whitelist()
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


def _get_cost_to_company_rate(doc, fallback_date=None):
	"""Return cost→company rate for doc (Manual Settings or Batch). Prefers doc.exchange_rate if set."""
	cost_ccy = getattr(doc, "cost_currency", None)
	company_ccy = getattr(doc, "company_currency", None)
	if not cost_ccy or not company_ccy or cost_ccy == company_ccy:
		return 1.0
	rate = flt(getattr(doc, "exchange_rate", 0))
	if rate:
		return rate
	date = getattr(doc, "exchange_rate_date", None) or fallback_date or frappe.utils.today()
	fetched = get_exchange_rate(cost_ccy, company_ccy, date)
	return flt(fetched) or 1.0


def _convert_amount(amount, should_convert, rate):
	"""Convert amount from cost_currency to company_currency if should_convert."""
	amt = flt(amount, 2)
	if not amt:
		return 0
	if should_convert and rate and rate != 1:
		return flt(amt * rate, 2)
	return amt


# ── Allocation helper for batch (value-weight, PDF p2-4) ───────────────────────


def allocate_shared_costs(batch_doc):
	"""
	Distribute header shared costs across child rows by value weight,
	except Fixed Cost which is per-unit x qty (SELLING PRICE 2.pdf p213):
	  weight_i = base_total_i / sum(base_total)
	  allocated_*_i = total_* * weight_i  (for bank/freight/clearing/tin/tout/overhead)
	  allocated_fixed_cost_i = fixed_cost_per_unit * qty_i

	All amounts converted to company currency per-field via convert_* flags
	(cost_currency → company_currency). Stored allocated_* are in company currency.

	Mutates batch_doc.items in place, also computes true_cost + tiers per row.
	"""
	items = batch_doc.items or []
	if not items:
		return

	rate = _get_cost_to_company_rate(batch_doc, getattr(batch_doc, "posting_date", None))

	# compute base_total per row first (unit_cost per row, with per-row convert flag)
	for row in items:
		convert_unit = bool(getattr(row, "convert_unit_cost", 0))
		unit_company = _convert_amount(row.unit_cost, convert_unit, rate)
		row.base_total = flt(flt(row.qty) * unit_company, 2)

	total_base = sum(flt(r.base_total) for r in items)
	if not total_base:
		return

	# collect header totals (in company currency after conversion per convert_* flags)
	t_bank = _convert_amount(
		batch_doc.total_bank_charges, getattr(batch_doc, "convert_total_bank_charges", 0), rate
	)
	t_freight = _convert_amount(batch_doc.total_freight, getattr(batch_doc, "convert_total_freight", 0), rate)
	t_clearing = _convert_amount(
		batch_doc.total_clearing_fees, getattr(batch_doc, "convert_total_clearing_fees", 0), rate
	)
	t_tin = _convert_amount(
		batch_doc.total_transport_in, getattr(batch_doc, "convert_total_transport_in", 0), rate
	)
	t_tout = _convert_amount(
		batch_doc.total_transport_out, getattr(batch_doc, "convert_total_transport_out", 0), rate
	)
	t_over = _convert_amount(batch_doc.total_overhead, getattr(batch_doc, "convert_total_overhead", 0), rate)
	fixed_per_unit = _convert_amount(
		batch_doc.total_fixed_cost, getattr(batch_doc, "convert_total_fixed_cost", 0), rate
	)

	# last-row delta correction to fix rounding (Fixed Cost excluded — per-unit)
	n = len(items)
	cum = {"bank": 0, "freight": 0, "clearing": 0, "tin": 0, "tout": 0, "over": 0}

	for idx, row in enumerate(items):
		is_last = idx == n - 1
		weight = flt(row.base_total) / total_base if total_base else 0
		qty = flt(row.qty)

		if is_last:
			row.allocated_bank_charges = flt(t_bank - cum["bank"], 2)
			row.allocated_freight = flt(t_freight - cum["freight"], 2)
			row.allocated_clearing_fees = flt(t_clearing - cum["clearing"], 2)
			row.allocated_transport_in = flt(t_tin - cum["tin"], 2)
			row.allocated_transport_out = flt(t_tout - cum["tout"], 2)
			row.allocated_overhead = flt(t_over - cum["over"], 2)
			row.allocated_fixed_cost = flt(fixed_per_unit * qty, 2)
		else:
			row.allocated_bank_charges = flt(t_bank * weight, 2)
			row.allocated_freight = flt(t_freight * weight, 2)
			row.allocated_clearing_fees = flt(t_clearing * weight, 2)
			row.allocated_transport_in = flt(t_tin * weight, 2)
			row.allocated_transport_out = flt(t_tout * weight, 2)
			row.allocated_overhead = flt(t_over * weight, 2)
			row.allocated_fixed_cost = flt(fixed_per_unit * qty, 2)
			cum["bank"] += row.allocated_bank_charges
			cum["freight"] += row.allocated_freight
			cum["clearing"] += row.allocated_clearing_fees
			cum["tin"] += row.allocated_transport_in
			cum["tout"] += row.allocated_transport_out
			cum["over"] += row.allocated_overhead

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
		row.true_cost_per_unit = (
			flt(row.true_cost / flt(row.qty), 2) if flt(row.qty) else flt(row.true_cost, 2)
		)

		tiers = compute_tiers(
			row.true_cost_per_unit,
			target_margin_pct=row.target_margin_pct,
			commission_pct=batch_doc.commission_pct,
			wht_pct=batch_doc.wht_pct,
		)
		row.basic_rate = flt(tiers.get("basic_rate") or 0, 2)
		row.target_rate = flt(tiers.get("target_rate") or 0, 2)
		row.rate_15 = flt(tiers.get("rate_15") or 0, 2)
		row.rate_30 = flt(tiers.get("rate_30") or 0, 2)
		row.rate_45 = flt(tiers.get("rate_45") or 0, 2)
		row.rate_commission = flt(tiers.get("rate_commission") or 0, 2)
		row.rate_commission_tax = flt(tiers.get("rate_commission_tax") or 0, 2)
		row.rate_target_commission = flt(tiers.get("rate_target_commission") or 0, 2)
		row.rate_target_commission_tax = flt(tiers.get("rate_target_commission_tax") or 0, 2)
		row.final_rate_per_unit = flt(tiers.get("final_rate_per_unit") or 0, 2)
		row.final_total = flt(flt(row.final_rate_per_unit) * flt(row.qty), 2)


def recompute_manual_estimate(doc):
	"""Compute tiers for a single Manual-mode Item Pricing Settings doc (cost_currency → company)."""
	qty = flt(doc.manual_qty) or 1
	rate = _get_cost_to_company_rate(doc)

	if flt(doc.estimated_true_cost_override):
		convert_override = bool(getattr(doc, "convert_estimated_true_cost_override", 0))
		override_total_company = _convert_amount(doc.estimated_true_cost_override, convert_override, rate)
		true_cost = flt(override_total_company / qty, 2) if qty > 1 else flt(override_total_company, 2)
	else:
		base_company = (
			_convert_amount(doc.estimated_base_rate, getattr(doc, "convert_estimated_base_rate", 0), rate)
			* qty
		)
		fixed_total = (
			_convert_amount(doc.manual_fixed_cost, getattr(doc, "convert_manual_fixed_cost", 0), rate) * qty
		)
		other_totals = (
			_convert_amount(doc.manual_bank_charges, getattr(doc, "convert_manual_bank_charges", 0), rate)
			+ _convert_amount(doc.manual_freight, getattr(doc, "convert_manual_freight", 0), rate)
			+ _convert_amount(doc.manual_clearing_fees, getattr(doc, "convert_manual_clearing_fees", 0), rate)
			+ _convert_amount(doc.manual_transport_in, getattr(doc, "convert_manual_transport_in", 0), rate)
			+ _convert_amount(doc.manual_transport_out, getattr(doc, "convert_manual_transport_out", 0), rate)
			+ _convert_amount(doc.manual_overhead, getattr(doc, "convert_manual_overhead", 0), rate)
		)
		true_cost_total = base_company + other_totals + fixed_total
		true_cost = flt(true_cost_total / qty, 2) if qty else flt(true_cost_total, 2)
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
		"current_valuation_rate": flt(true_cost, 4)
		if doc.pricing_mode == "Auto"
		else flt(doc.current_valuation_rate, 4),
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
		"last_updated": now_datetime(),
	}
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

	val_rate = _get_current_valuation_rate(item_code)
	if not val_rate:
		return

	tiers = compute_tiers(
		flt(val_rate, 4),
		target_margin_pct=flt(settings.target_margin_pct) or None,
		commission_pct=flt(settings.commission_pct) or None,
		wht_pct=flt(settings.wht_pct) or None,
	)
	standard_rate = get_standard_rate(tiers, settings.standard_selling_source_tier)

	# Standard Selling is the live price
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
