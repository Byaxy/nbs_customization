# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Delivery progress for placement contracts."""

import frappe
from frappe.utils import flt


def delivered_by_item(contract_name):
	rows = frappe.db.sql(
		"""
		SELECT dni.item_code, SUM(dni.qty) AS qty
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
	reagent_required = reagent_delivered = 0
	consumable_required = consumable_delivered = 0
	for line in contract.contract_reagent_lines:
		required = flt(line.qty_required_total)
		got = flt(delivered.get(line.item_code))
		line.delivered_qty = got
		line.remaining_qty = max(required - got, 0)
		reagent_required += required
		reagent_delivered += got
	for line in contract.contract_consumable_lines:
		required = flt(line.qty_required_total)
		got = flt(delivered.get(line.item_code))
		line.delivered_qty = got
		line.remaining_qty = max(required - got, 0)
		consumable_required += required
		consumable_delivered += got
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
