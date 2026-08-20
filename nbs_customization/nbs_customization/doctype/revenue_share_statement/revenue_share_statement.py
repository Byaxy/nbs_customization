# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from nbs_customization.utils.placement.recovery import recompute_contract_recovery
import datetime
import calendar

REVENUE_SHARE_FEE_ITEM = "REVENUE-SHARE-FEE"


class RevenueShareStatement(Document):
	def on_submit(self):
		self.status = "Invoiced"
		self.db_set("status", "Invoiced")
		recompute_contract_recovery(self.contract)


@frappe.whitelist()
def generate_revenue_share_statement(contract_name, period):
	contract = frappe.get_doc("Instrument Placement Contract", contract_name)
	if contract.contract_type != "CPT":
		frappe.throw(
			frappe._("Revenue Share Statement is only for CPT contracts.")
		)

	declared_volume = _resolve_declared_volume(contract, period)
	revenue_share_pct = (contract.revenue_share_pct or 0) / 100

	gross_revenue = contract.fixed_monthly_gross_revenue or 0
	our_share = gross_revenue * revenue_share_pct
	customer_share = gross_revenue - our_share

	existing = frappe.db.get_value(
		"Revenue Share Statement",
		{"contract": contract_name, "period": period},
		"name",
	)
	if existing:
		rss = frappe.get_doc("Revenue Share Statement", existing)
	else:
		rss = frappe.get_doc({
			"doctype": "Revenue Share Statement",
			"contract": contract_name,
			"period": period,
			"period_start": _period_start(period),
			"period_end": _period_end(period),
		})
		rss.insert(ignore_permissions=True)

	rss.declared_volume = declared_volume
	rss.gross_revenue = gross_revenue
	rss.our_share_amount = our_share
	rss.customer_share_amount = customer_share
	rss.invoiced_this_period = our_share

	rss.kits_to_deliver = _compute_kits_needed(contract, declared_volume)

	rss.save(ignore_permissions=True)

	if rss.kits_to_deliver > 0 and not rss.waybill_kit_dispatch:
		dn = _create_free_issue_delivery_note(contract, declared_volume)
		rss.waybill_kit_dispatch = dn.name

	if not rss.sales_invoice:
		si = _create_revenue_share_invoice(rss, contract)
		rss.sales_invoice = si.name

	rss.status = "Invoiced"
	rss.save(ignore_permissions=True)

	recompute_contract_recovery(contract_name)

	return rss.name


def _resolve_declared_volume(contract, period):
	period_start = _period_start(period)
	period_end = _period_end(period)

	amendment = frappe.db.get_all(
		"Contract Amendment",
		filters={
			"contract": contract.name,
			"status": "Effective",
			"effective_date": ("between", [period_start, period_end]),
		},
		fields=["new_declared_volume"],
		order_by="effective_date desc",
		limit=1,
	)
	if amendment:
		return amendment[0].new_declared_volume

	total_vol = sum(
		(line.monthly_test_volume or 0)
		for line in contract.contract_reagent_lines
	)
	return total_vol or 0


def _compute_kits_needed(contract, declared_volume):
	total_packs = 0
	for line in contract.contract_reagent_lines:
		tpp = frappe.db.get_value(
			"Reagent Specification", {"item": line.item_code}, "default_tests_per_pack"
		)
		if tpp:
			total_packs += declared_volume / tpp
	return total_packs


def _compute_kits_per_line(contract, declared_volume):
	result = {}
	for line in contract.contract_reagent_lines:
		tpp = frappe.db.get_value(
			"Reagent Specification", {"item": line.item_code}, "default_tests_per_pack"
		)
		if tpp:
			result[line.item_code] = declared_volume / tpp
	return result


def _create_free_issue_delivery_note(contract, declared_volume):
	kits_per_line = _compute_kits_per_line(contract, declared_volume)
	dn = frappe.get_doc({
		"doctype": "Delivery Note",
		"customer": contract.customer,
		"custom_instrument_placement_contract": contract.name,
		"custom_placement_transaction_type": "Contract Free Issue",
		"posting_date": frappe.utils.today(),
		"items": [
			{
				"item_code": item_code,
				"qty": qty,
				"rate": 0,
			}
			for item_code, qty in kits_per_line.items()
		],
	})
	dn.insert(ignore_permissions=True)
	dn.submit()
	return dn


def _create_revenue_share_invoice(rss, contract):
	si = frappe.get_doc({
		"doctype": "Sales Invoice",
		"customer": contract.customer,
		"custom_instrument_placement_contract": contract.name,
		"custom_placement_transaction_type": "Contract Reagent Sale",
		"custom_counts_toward_recovery": 1,
		"posting_date": frappe.utils.today(),
		"items": [
			{
				"item_code": REVENUE_SHARE_FEE_ITEM,
				"qty": 1,
				"rate": rss.our_share_amount,
			}
		],
	})
	si.insert(ignore_permissions=True)
	si.submit()
	return si


def _period_start(period):
	parts = period.split("-")
	return datetime.date(int(parts[0]), int(parts[1]), 1)


def _period_end(period):
	start = _period_start(period)
	last_day = calendar.monthrange(start.year, start.month)[1]
	return datetime.date(start.year, start.month, last_day)
