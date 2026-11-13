# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Shared test-level terms for pricing and revenue calculations."""

from frappe.utils import flt


def unique_test_terms(lines, price_field=None):
	terms = {}
	for line in lines:
		test_parameter = line.get("test_parameter")
		if not test_parameter:
			continue
		volume = flt(line.get("monthly_test_volume"))
		price = flt(line.get(price_field)) if price_field else 0
		current = terms.get(test_parameter)
		if not current:
			terms[test_parameter] = {"volume": volume, "price": price}
			continue
		current["volume"] = max(current["volume"], volume)
		if price:
			current["price"] = current["price"] or price
	return terms


def monthly_test_count(lines):
	return sum(term["volume"] for term in unique_test_terms(lines).values())


def test_revenue(lines, term_months, price_field):
	return sum(
		term["volume"] * flt(term_months) * term["price"]
		for term in unique_test_terms(lines, price_field).values()
	)


def allocated_test_volumes(lines, declared_volume):
	terms = unique_test_terms(lines, "monthly_test_volume")
	total = sum(term["volume"] for term in terms.values())
	if not total:
		return {}
	return {
		test_parameter: flt(declared_volume) * term["volume"] / total
		for test_parameter, term in terms.items()
	}
