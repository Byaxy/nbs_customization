# Contract chain + lifecycle documents for placement TDD backfill (Phase 01).
# Builds on placement_fixtures masters; tests roll back, no cleanup.

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

from nbs_customization.tests.placement_fixtures import (
	BANK_ACCOUNT,
	COMPANY,
	SITE_LOCATION,
	STORAGE_LOCATION,
	WAREHOUSE,
	link_reagent_to_spec,
	make_analyzer,
	make_customer,
	make_reagent,
	make_site,
)


def make_worksheet(prefix, analyzer, reagent, param, customer, contract_type="RRA"):
	# Submitted-ready worksheet; submit() flips status to Approved.
	ws = frappe.get_doc(
		{
			"doctype": "Instrument Pricing Worksheet",
			"naming_series": "NBSIPWS-.YYYY./.####",
			"analyzer_pid": analyzer["item"].name,
			"contract_type": contract_type,
			"calculation_output_type": "Markup Factor on Reagent Price",
			"analyzer_landed_cost": 5000,
			"contract_years": 2,
			"profit_margin_pct": 20,
			"customer": customer.name,
			"annual_interest_rate": 5 if contract_type == "RLO" else 0,
			"reagent_lines": [
				{
					"item_code": reagent.name,
					"test_parameter": param["param"].name,
					"monthly_test_volume": 50,
					"cogs_per_pack": 50,
					"tests_per_pack": 100,
				}
			],
		}
	).insert()
	ws.submit()
	return ws


def make_asset_category(prefix):
	name = f"{prefix}-CAT"
	if frappe.db.exists("Asset Category", name):
		return frappe.get_doc("Asset Category", name)
	return frappe.get_doc(
		{
			"doctype": "Asset Category",
			"asset_category_name": name,
			"accounts": [
				{
					"company_name": COMPANY,
					"fixed_asset_account": "Capital Equipment - NBS",
					"accumulated_depreciation_account": "Accumulated Depreciation - NBS",
					"depreciation_expense_account": "Depreciation - NBS",
				}
			],
			"finance_books": [
				{
					"depreciation_method": "Straight Line",
					"frequency_of_depreciation": 12,
					"total_number_of_depreciations": 3,
				}
			],
		}
	).insert(ignore_permissions=True)


def make_asset(prefix, category, serial, analyzer_item, submitted=True):
	# Submitted asset carries a live depreciation schedule (OTR halt tests need it).
	# A real Serial No backs the serial string (OTR fetches it into a Link field).
	frappe.get_doc(
		{
			"doctype": "Serial No",
			"serial_no": serial,
			"item_code": analyzer_item,
			"company": COMPANY,
		}
	).insert(ignore_if_duplicate=True)
	capital = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": f"{prefix}-CAP",
			"item_group": "Products",
			"is_fixed_asset": 1,
			"is_stock_item": 0,
			"asset_category": category.name,
		}
	).insert(ignore_if_duplicate=True)
	asset = frappe.get_doc(
		{
			"doctype": "Asset",
			"asset_name": f"{prefix}-ASSET",
			"item_code": capital.name,
			"company": COMPANY,
			"asset_category": category.name,
			"location": STORAGE_LOCATION,
			"purchase_date": "2026-01-05",
			"available_for_use_date": "2026-01-05",
			"gross_purchase_amount": 5000,
			"net_purchase_amount": 5000,
			"custom_serial_no": serial,
			"calculate_depreciation": 1,
			"finance_books": [
				{
					"depreciation_method": "Straight Line",
					"frequency_of_depreciation": 12,
					"total_number_of_depreciations": 3,
					"depreciation_start_date": frappe.utils.today(),
				}
			],
		}
	).insert()
	if submitted:
		asset.submit()
	return asset


def make_contract(
	prefix,
	analyzer,
	reagent,
	param,
	customer,
	site,
	asset,
	worksheet,
	serial,
	contract_type="RRA",
	target=12000,
	breach=3,
	grace=0,
	agreed_price=0,
	share_pct=0,
	minqty=10,
):
	# Draft contract with one reagent line; submit() activates it.
	ct = frappe.get_doc(
		{
			"doctype": "Instrument Placement Contract",
			"naming_series": "NBSIPC-.YYYY./.####",
			"contract_title": f"{prefix}-CT",
			"contract_type": contract_type,
			"customer": customer.name,
			"customer_site": site.name,
			"asset": asset.name,
			"serial_no": serial,
			"analyzer_pid": analyzer["item"].name,
			"analyzer_description": "Test analyzer",
			"pricing_worksheet": worksheet.name,
			"start_date": "2026-01-01",
			"end_date": "2027-12-31",
			"total_recovery_target": target,
			"breach_threshold": breach,
			"grace_period_days": grace,
			"revenue_share_pct": share_pct,
			"contract_reagent_lines": [
				{
					"item_code": reagent.name,
					"test_parameter": param["param"].name,
					"contract_price": 150,
					"standard_price": 50,
					"monthly_test_volume": 100,
					"min_monthly_qty": minqty,
					"cogs_per_unit": 50,
					"agreed_test_price": agreed_price,
				}
			],
		}
	).insert()
	ct.submit()
	return ct


def make_contract_kit(prefix, contract_type="RRA", **overrides):
	# Full chain in one call; returns dict of every doc for assertions.
	analyzer = make_analyzer(prefix)
	reagent = make_reagent(f"{prefix}-R")
	link_reagent_to_spec(analyzer["item"].name, analyzer["param"], reagent)
	customer = make_customer(prefix)
	worksheet = make_worksheet(prefix, analyzer, reagent, analyzer, customer, contract_type)
	site = make_site(prefix)
	category = make_asset_category(prefix)
	serial = f"{prefix}-SN"
	asset = make_asset(prefix, category, serial, analyzer["item"].name)
	contract = make_contract(
		prefix,
		analyzer,
		reagent,
		analyzer,
		customer,
		site,
		asset,
		worksheet,
		serial,
		contract_type,
		**overrides,
	)
	return {
		"analyzer": analyzer,
		"reagent": reagent,
		"customer": customer,
		"worksheet": worksheet,
		"site": site,
		"category": category,
		"asset": asset,
		"contract": contract,
	}


def make_si(ctx, qty, rate, posting_date, ttype, counts=1):
	# Site mandates SO links on SI items — every fixture SI ships with its order.
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": COMPANY,
			"customer": ctx["customer"].name,
			"transaction_date": posting_date,
			"delivery_date": posting_date,
			"custom_instrument_placement_contract": ctx["contract"].name,
			"custom_placement_transaction_type": ttype,
			"items": [
				{
					"item_code": ctx["reagent"].name,
					"qty": qty,
					"rate": rate,
					"warehouse": WAREHOUSE,
				}
			],
		}
	).insert()
	so.submit()
	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": COMPANY,
			"customer": ctx["customer"].name,
			"posting_date": posting_date,
			"set_posting_time": 1,
			"custom_instrument_placement_contract": ctx["contract"].name,
			"custom_counts_toward_recovery": counts,
			"custom_placement_transaction_type": ttype,
			"items": [
				{
					"item_code": ctx["reagent"].name,
					"qty": qty,
					"rate": rate,
					"sales_order": so.name,
					"so_detail": so.items[0].name,
				}
			],
		}
	).insert()
	si.submit()
	return si


def make_payment(si):
	pe = get_payment_entry("Sales Invoice", si.name)
	pe.paid_to = BANK_ACCOUNT
	pe.mode_of_payment = "Wire Transfer"
	pe.reference_no = f"REF-{si.name}"
	pe.reference_date = frappe.utils.today()
	pe.insert(ignore_permissions=True)
	pe.submit()
	return pe


def make_deployed(ctx, deployment_date="2026-02-01"):
	# Side effects fire on status change — insert off-Deployed, then transition.
	dep = frappe.get_doc(
		{
			"doctype": "Analyzer Deployment",
			"naming_series": "NBSAD-.YYYY./.####",
			"contract": ctx["contract"].name,
			"asset": ctx["asset"].name,
			"customer": ctx["customer"].name,
			"customer_site": ctx["site"].name,
			"asset_location": SITE_LOCATION,
			"asset_storage_location": STORAGE_LOCATION,
			"deployment_date": deployment_date,
			"deployment_status": "Under Service",
		}
	).insert()
	dep.deployment_status = "Deployed"
	dep.save()
	return dep
