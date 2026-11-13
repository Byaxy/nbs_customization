# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Delivery progress for placement contracts."""

import frappe
from frappe.utils import flt


def delivered_by_item(contract_name):
	rows = frappe.db.sql(
		"""
		SELECT dni.item_code, SUM(COALESCE(dni.stock_qty, dni.qty)) AS qty
		FROM `tabDelivery Note Item` dni
		JOIN `tabDelivery Note` dn ON dn.name = dni.parent
		WHERE dn.docstatus = 1
			AND IFNULL(dn.is_return, 0) = 0
			AND dn.custom_instrument_placement_contract = %s
		GROUP BY dni.item_code
		""",
		(contract_name,),
		as_dict=True,
	)
	return {row["item_code"]: flt(row["qty"]) for row in rows}


def apply_progress(contract):
	delivered = delivered_by_item(contract.name) if not contract.is_new() else {}
	lines = list(contract.contract_reagent_lines) + list(contract.contract_consumable_lines)
	by_item = {}
	for line in lines:
		if line.item_code:
			by_item.setdefault(line.item_code, []).append(line)

	for item_code, item_lines in by_item.items():
		total_required = sum(flt(line.qty_required_total) for line in item_lines)
		total_delivered = flt(delivered.get(item_code))
		for line in item_lines:
			required = flt(line.qty_required_total)
			allocated = total_delivered * required / total_required if total_required else 0
			line.delivered_qty = allocated
			line.remaining_qty = max(required - allocated, 0)

	reagent_required = sum(flt(line.qty_required_total) for line in contract.contract_reagent_lines)
	reagent_delivered = sum(flt(line.delivered_qty) for line in contract.contract_reagent_lines)
	consumable_required = sum(flt(line.qty_required_total) for line in contract.contract_consumable_lines)
	consumable_delivered = sum(flt(line.delivered_qty) for line in contract.contract_consumable_lines)

	contract.progress_reagent_required = reagent_required
	contract.progress_reagent_delivered = reagent_delivered
	contract.progress_reagent_remaining = max(reagent_required - reagent_delivered, 0)
	contract.progress_consumable_required = consumable_required
	contract.progress_consumable_delivered = consumable_delivered
	contract.progress_consumable_remaining = max(consumable_required - consumable_delivered, 0)


def update_contract_progress(contract_name):
	if not contract_name or not frappe.db.exists("Instrument Placement Contract", contract_name):
		return
	contract = frappe.get_doc("Instrument Placement Contract", contract_name)
	apply_progress(contract)
	contract.db_update()
	for line in contract.contract_reagent_lines:
		line.db_update()
	for line in contract.contract_consumable_lines:
		line.db_update()
