# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Pure pricing engine for analyzer placement.

No Frappe imports. Callers pass plain values and persist the results. Keeping
the maths free of framework state makes the golden cases cheap to test.
"""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

MONEY = Decimal("0.01")


def _decimal(value):
	return Decimal(str(value or 0))


def _money(value):
	return float(_decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP))


def ceil_packs(value):
	value = _decimal(value)
	if value <= 0:
		return 0
	return int(value.to_integral_value(rounding=ROUND_CEILING))


def declared_packs(monthly_tests, term_months, reportable_tests_per_pack):
	reportable = _decimal(reportable_tests_per_pack)
	if reportable <= 0:
		raise ValueError("Reportable tests per pack must be positive.")
	return ceil_packs(_decimal(monthly_tests) * _decimal(term_months) / reportable)


def capital_costs(
	analyzer_standard_selling_price,
	annual_service_rate_pct,
	annual_interest_rate_pct,
	term_months,
	include_interest,
):
	analyzer = _decimal(analyzer_standard_selling_price)
	term_months = _decimal(term_months)
	term_years = term_months / 12
	maintenance = analyzer * _decimal(annual_service_rate_pct) / 100 * term_years
	interest = 0
	if include_interest:
		interest = analyzer * _decimal(annual_interest_rate_pct) / 100 * term_years
	return _money(maintenance), _money(interest)


def target_amounts(
	analyzer_standard_selling_price,
	reagent_value,
	consumable_value,
	maintenance_cost,
	interest_amount,
	profit_margin_pct,
	wht_rate_pct,
):
	analyzer = _decimal(analyzer_standard_selling_price)
	reagent = _decimal(reagent_value)
	consumable = _decimal(consumable_value)
	maintenance = _decimal(maintenance_cost)
	interest = _decimal(interest_amount)

	standard_sale_base = analyzer + reagent + consumable + maintenance
	total_cost_base = standard_sale_base + interest
	profit = total_cost_base * _decimal(profit_margin_pct) / 100
	net_target = total_cost_base + profit
	rate = _decimal(wht_rate_pct)
	if rate < 0 or rate >= 100:
		raise ValueError("Withholding tax rate must be between 0 and 100.")
	wht_amount = net_target * rate / (100 - rate)
	gross_target = net_target + wht_amount
	return {
		"standard_sale_base": _money(standard_sale_base),
		"total_cost_base": _money(total_cost_base),
		"profit_amount": _money(profit),
		"net_revenue_target": _money(net_target),
		"wht_amount": _money(wht_amount),
		"final_revenue_target": _money(gross_target),
		"fixed_cost_to_recover": _money(analyzer + interest + maintenance),
	}
