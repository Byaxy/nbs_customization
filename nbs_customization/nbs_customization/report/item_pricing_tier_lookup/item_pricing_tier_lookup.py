# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def execute(filters=None):
	"""Columns: Item + tiers + live Standard Selling + audit."""
	filters = filters or {}
	columns = [
		{"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{
			"label": "Category",
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 120,
		},
		{"label": "Mode", "fieldname": "pricing_mode", "fieldtype": "Data", "width": 70},
		{"label": "True Cost", "fieldname": "true_cost", "fieldtype": "Currency", "width": 110},
		{"label": "Basic", "fieldname": "basic_rate", "fieldtype": "Currency", "width": 110},
		{"label": "15%", "fieldname": "rate_15", "fieldtype": "Currency", "width": 110},
		{"label": "30% (Std)", "fieldname": "rate_30", "fieldtype": "Currency", "width": 110},
		{"label": "45%", "fieldname": "rate_45", "fieldtype": "Currency", "width": 110},
		{"label": "Commission", "fieldname": "rate_commission", "fieldtype": "Currency", "width": 110},
		{
			"label": "Commission+Tax",
			"fieldname": "rate_commission_tax",
			"fieldtype": "Currency",
			"width": 120,
		},
		{"label": "Final", "fieldname": "final_rate_per_unit", "fieldtype": "Currency", "width": 110},
		{
			"label": "Standard Selling Source",
			"fieldname": "standard_selling_source_tier",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": "Suggested (Std)",
			"fieldname": "suggested_selling_price",
			"fieldtype": "Currency",
			"width": 120,
		},
		{"label": "Current Std", "fieldname": "current_selling_price", "fieldtype": "Currency", "width": 120},
		{"label": "Updated", "fieldname": "last_updated", "fieldtype": "Datetime", "width": 150},
		{
			"label": "Batch",
			"fieldname": "reference_quotation_batch",
			"fieldtype": "Link",
			"options": "Item Pricing Quotation Batch",
			"width": 130,
		},
	]

	conds = ["1=1"]
	vals = {}

	if filters.get("item_code"):
		conds.append("ips.item_code = %(item_code)s")
		vals["item_code"] = filters["item_code"]
	if filters.get("item_group"):
		conds.append("ips.item_group = %(item_group)s")
		vals["item_group"] = filters["item_group"]
	if filters.get("pricing_mode"):
		conds.append("ips.pricing_mode = %(pricing_mode)s")
		vals["pricing_mode"] = filters["pricing_mode"]

	where = " AND ".join(conds)

	rows = frappe.db.sql(
		f"""
		SELECT
			ips.item_code,
			ips.item_group,
			ips.pricing_mode,
			ips.standard_selling_source_tier,
			ips.suggested_selling_price,
			ips.current_selling_price,
			ips.basic_rate, ips.rate_15, ips.rate_30, ips.rate_45,
			ips.rate_commission, ips.rate_commission_tax, ips.final_rate_per_unit,
			ips.last_updated,
			ips.reference_quotation_batch,
			ips.current_valuation_rate,
			ips.manual_true_cost,
			ips.quote_currency,
			ips.company_currency,
			i.item_name
		FROM `tabItem Pricing Settings` ips
		LEFT JOIN `tabItem` i ON i.name = ips.item_code
		WHERE {where}
		ORDER BY ips.modified DESC
		""",
		vals,
		as_dict=True,
	)

	data = []
	for r in rows:
		true_cost = (
			flt(r.manual_true_cost)
			if r.pricing_mode == "Manual" and flt(r.manual_true_cost)
			else flt(r.current_valuation_rate)
		)
		data.append(
			{
				"item_code": r.item_code,
				"item_name": r.item_name,
				"item_group": r.item_group,
				"pricing_mode": r.pricing_mode,
				"true_cost": true_cost,
				"basic_rate": r.basic_rate,
				"rate_15": r.rate_15,
				"rate_30": r.rate_30,
				"rate_45": r.rate_45,
				"rate_commission": r.rate_commission,
				"rate_commission_tax": r.rate_commission_tax,
				"final_rate_per_unit": r.final_rate_per_unit,
				"standard_selling_source_tier": r.standard_selling_source_tier,
				"suggested_selling_price": r.suggested_selling_price,
				"current_selling_price": r.current_selling_price,
				"last_updated": r.last_updated,
				"reference_quotation_batch": r.reference_quotation_batch,
			}
		)

	return columns, data
