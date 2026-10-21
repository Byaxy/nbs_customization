# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from math import ceil

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from nbs_customization.utils.placement.periods import (
	period_end,
	period_start,
	posting_date_for_period,
	validate_period,
)
from nbs_customization.utils.placement.permissions import (
	FINANCE_MANAGERS,
	require_contract_access,
	require_roles,
)
from nbs_customization.utils.placement.recovery import recompute_contract_recovery

REVENUE_SHARE_FEE_ITEM = "REVENUE-SHARE-FEE"


class RevenueShareStatement(Document):
	def on_submit(self):
		self.status = "Invoiced"
		self.db_set("status", "Invoiced")
		recompute_contract_recovery(self.contract)


@frappe.whitelist()
def generate_revenue_share_statement(contract_name, period):
	validate_period(period)
	require_roles(*FINANCE_MANAGERS)
	require_contract_access(contract_name, "write")
	contract = frappe.get_doc("Instrument Placement Contract", contract_name)
	if contract.contract_type != "CPT":
		frappe.throw(frappe._("Revenue Share Statement is only for CPT contracts."))
	if contract.contract_status != "Active":
		frappe.throw(
			frappe._("Revenue Share Statement requires an Active contract (current: {0}).").format(
				contract.contract_status
			)
		)

	declared_volume, amendment_name = _resolve_declared_volume(contract, period)
	if declared_volume <= 0:
		frappe.throw(frappe._("Declared test volume must be greater than zero."))

	allocated = _allocate_declared_volume(contract, declared_volume)
	gross_revenue = sum(volume * (line.agreed_test_price or 0) for line, volume in allocated)
	revenue_share_pct = (contract.revenue_share_pct or 0) / 100
	our_share = gross_revenue * revenue_share_pct
	customer_share = gross_revenue - our_share
	kits_per_line = _compute_kits_per_line(contract, declared_volume)
	kits_to_deliver = sum(kits_per_line.values())

	existing = frappe.db.get_value(
		"Revenue Share Statement",
		{"contract": contract_name, "period": period},
		"name",
	)
	if existing:
		rss = frappe.get_doc("Revenue Share Statement", existing)
		_assert_regeneration_safe(rss, declared_volume, gross_revenue, our_share, kits_per_line)
	else:
		rss = frappe.get_doc(
			{
				"doctype": "Revenue Share Statement",
				"contract": contract_name,
				"period": period,
				"period_start": period_start(period),
				"period_end": period_end(period),
			}
		)
		rss.insert(ignore_permissions=True)

	rss.contract_type = contract.contract_type
	rss.customer = contract.customer
	rss.customer_name = contract.customer_name
	rss.asset = contract.asset
	rss.revenue_share_pct = revenue_share_pct * 100
	rss.declared_volume = declared_volume
	rss.gross_revenue = gross_revenue
	rss.our_share_amount = our_share
	rss.customer_share_amount = customer_share
	rss.invoiced_this_period = our_share
	rss.kits_to_deliver = kits_to_deliver
	rss.active_amendment = amendment_name
	rss.save(ignore_permissions=True)

	if rss.kits_to_deliver > 0 and not rss.waybill_kit_dispatch:
		company = _resolve_company(contract)
		order_name = _ensure_free_issue_order(contract, company, declared_volume)
		dn = _create_free_issue_delivery_note(contract, company, order_name, declared_volume)
		rss.waybill_kit_dispatch = dn.name
		rss.save(ignore_permissions=True)

	if not rss.sales_invoice:
		company = _resolve_company(contract)
		si = _create_revenue_share_invoice(rss, contract, company)
		rss.sales_invoice = si.name

	rss.status = "Invoiced"
	rss.save(ignore_permissions=True)

	recompute_contract_recovery(contract_name)

	return rss.name


def _resolve_declared_volume(contract, period):
	amendment = frappe.db.get_all(
		"Contract Amendment",
		filters={
			"contract": contract.name,
			"status": "Effective",
			"effective_date": ("between", [period_start(period), period_end(period)]),
		},
		fields=["name", "new_declared_volume"],
		order_by="effective_date desc",
		limit=1,
	)
	if amendment and amendment[0].new_declared_volume:
		return amendment[0].new_declared_volume, amendment[0].name

	total_vol = sum((line.monthly_test_volume or 0) for line in contract.contract_reagent_lines)
	return total_vol, None


def _allocate_declared_volume(contract, declared_volume):
	"""Split the period's declared volume by each line's contracted share."""
	lines = list(contract.contract_reagent_lines)
	if not lines:
		frappe.throw(frappe._("Contract has no reagent lines to allocate volume to."))

	total_contract_volume = sum((line.monthly_test_volume or 0) for line in lines)
	if total_contract_volume <= 0:
		share = declared_volume / len(lines)
		return [(line, share) for line in lines]

	return [
		(line, declared_volume * (line.monthly_test_volume or 0) / total_contract_volume) for line in lines
	]


def _compute_kits_per_line(contract, declared_volume):
	volumes = {}
	for line, volume in _allocate_declared_volume(contract, declared_volume):
		volumes[line.item_code] = volumes.get(line.item_code, 0) + volume

	result = {}
	for item_code, volume in volumes.items():
		tpp = frappe.db.get_value(
			"Reagent Specification",
			{"item": item_code},
			"default_tests_per_pack",
		)
		if tpp and volume > 0:
			result[item_code] = ceil(volume / tpp)
	return result


def _assert_regeneration_safe(rss, declared_volume, gross_revenue, our_share, kits_per_line):
	_assert_invoice_regeneration_safe(rss, declared_volume, gross_revenue, our_share)
	_assert_dispatch_regeneration_safe(rss, kits_per_line)


def _assert_invoice_regeneration_safe(rss, declared_volume, gross_revenue, our_share):
	if not rss.sales_invoice:
		return
	if frappe.db.get_value("Sales Invoice", rss.sales_invoice, "docstatus") != 1:
		rss.sales_invoice = None
		return
	if (
		abs((rss.declared_volume or 0) - declared_volume) <= 0.01
		and abs((rss.gross_revenue or 0) - gross_revenue) <= 0.01
		and abs((rss.our_share_amount or 0) - our_share) <= 0.01
	):
		return
	frappe.throw(
		frappe._(
			"Revenue Share Statement {0} already has invoice {1}. "
			"Cancel or delete it before regenerating with different values."
		).format(frappe.bold(rss.name), frappe.bold(rss.sales_invoice))
	)


def _assert_dispatch_regeneration_safe(rss, kits_per_line):
	if not rss.waybill_kit_dispatch:
		return
	dn = frappe.get_doc("Delivery Note", rss.waybill_kit_dispatch)
	if dn.docstatus != 1:
		rss.waybill_kit_dispatch = None
		return
	if _quantities_match(_dispatch_qty_by_item(dn), _positive_kits(kits_per_line)):
		return
	frappe.throw(
		frappe._(
			"Revenue Share Statement {0} has Delivery Note {1} with different kit quantities. "
			"Cancel the Delivery Note before regenerating with changed values."
		).format(frappe.bold(rss.name), frappe.bold(dn.name))
	)


def _dispatch_qty_by_item(dn):
	quantities = {}
	for row in dn.items:
		quantities[row.item_code] = quantities.get(row.item_code, 0) + flt(row.qty)
	return quantities


def _positive_kits(kits_per_line):
	return {item_code: flt(qty) for item_code, qty in kits_per_line.items() if flt(qty) > 0}


def _quantities_match(left, right):
	if left.keys() != right.keys():
		return False
	return all(abs(left[item_code] - right[item_code]) <= 0.01 for item_code in left)


def _resolve_company(contract):
	# RSS has no company field — inherit the capitalized asset's, else site default.
	if contract.asset:
		company = frappe.db.get_value("Asset", contract.asset, "company")
		if company:
			return company
	return frappe.db.get_single_value("Global Defaults", "default_company")


def _resolve_source_warehouse(item_code, company):
	wh = frappe.db.get_value("Item Default", {"parent": item_code, "company": company}, "default_warehouse")
	if wh:
		return wh
	wh = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
	if not wh:
		frappe.throw(frappe._("No stock warehouse found for company {0}.").format(frappe.bold(company)))
	return wh


def _ensure_free_issue_order(contract, company, declared_volume):
	# Site requires SO links on SI/DN items — free issue ships against a zero-value order.
	kits_per_line = _compute_kits_per_line(contract, declared_volume)
	lines = [
		{
			"item_code": item_code,
			"qty": qty,
			"rate": 0,
			# Explicit zero price_list_rate: ERPNext reprices falsy rates from
			# the price list during validate (taxes_and_totals.calculate_item_rate).
			"price_list_rate": 0,
			"warehouse": _resolve_source_warehouse(item_code, company),
		}
		for item_code, qty in kits_per_line.items()
		if qty > 0
	]
	if not lines:
		return None
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": company,
			"customer": contract.customer,
			"transaction_date": frappe.utils.today(),
			"delivery_date": frappe.utils.today(),
			"custom_instrument_placement_contract": contract.name,
			"custom_placement_transaction_type": "Contract Free Issue",
			"items": lines,
		}
	)
	so.insert(ignore_permissions=True)
	so.submit()
	return so.name


def _create_free_issue_delivery_note(contract, company, order_name, declared_volume):
	kits_per_line = _compute_kits_per_line(contract, declared_volume)
	so_items = {}
	if order_name:
		so_items = {i.item_code: i.name for i in frappe.get_doc("Sales Order", order_name).items}
	dn = frappe.get_doc(
		{
			"doctype": "Delivery Note",
			"company": company,
			"customer": contract.customer,
			"custom_instrument_placement_contract": contract.name,
			"custom_placement_transaction_type": "Contract Free Issue",
			"posting_date": frappe.utils.today(),
			"set_posting_time": 1,
			"items": [
				{
					"item_code": item_code,
					"qty": qty,
					"rate": 0,
					# See _ensure_free_issue_order: keep price_list_rate zero so
					# core repricing leaves the free-issue rate alone.
					"price_list_rate": 0,
					"warehouse": _resolve_source_warehouse(item_code, company),
					"against_sales_order": order_name,
					"so_detail": so_items.get(item_code),
				}
				for item_code, qty in kits_per_line.items()
				if qty > 0
			],
		}
	)
	dn.insert(ignore_permissions=True)
	dn.submit()
	return dn


def _create_revenue_share_invoice(rss, contract, company):
	# Site mandates SO links on SI items — bill the fee against its own order.
	fee_order = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": company,
			"customer": contract.customer,
			"transaction_date": frappe.utils.today(),
			"delivery_date": frappe.utils.today(),
			"custom_instrument_placement_contract": contract.name,
			"custom_placement_transaction_type": "Contract Reagent Sale",
			"items": [
				{
					"item_code": REVENUE_SHARE_FEE_ITEM,
					"qty": 1,
					"rate": rss.our_share_amount,
				}
			],
		}
	)
	fee_order.insert(ignore_permissions=True)
	fee_order.submit()
	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": contract.customer,
			"custom_instrument_placement_contract": contract.name,
			"custom_placement_transaction_type": "Contract Reagent Sale",
			"custom_counts_toward_recovery": 1,
			"posting_date": posting_date_for_period(rss.period),
			"set_posting_time": 1,
			"items": [
				{
					"item_code": REVENUE_SHARE_FEE_ITEM,
					"qty": 1,
					"rate": rss.our_share_amount,
					"sales_order": fee_order.name,
					"so_detail": fee_order.items[0].name,
				}
			],
		}
	)
	si.insert(ignore_permissions=True)
	si.submit()
	return si
