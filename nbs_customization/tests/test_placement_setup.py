# Phase 02 — seeders, permissions, serial-mandatory, redeploy, scrap, outright sale.

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.setup import (
	_ensure_brand_others,
	_ensure_equipment_category,
	create_nbs_capital_asset_item,
	create_revenue_share_fee_item,
	create_shortfall_penalty_item,
)
from nbs_customization.tests.placement_contracts import make_worksheet
from nbs_customization.tests.placement_fixtures import (
	COMPANY,
	WAREHOUSE,
	link_reagent_to_spec,
	make_analyzer,
	make_customer,
	make_reagent,
	make_serial,
	make_site,
	skip_test_record_bootstrap,
)


def _seed_all():
	_ensure_brand_others()
	_ensure_equipment_category()
	create_revenue_share_fee_item()
	create_shortfall_penalty_item()
	create_nbs_capital_asset_item()


def _draft_contract(prefix, analyzer, reagent, param, customer, site, worksheet):
	return frappe.get_doc(
		{
			"doctype": "Instrument Placement Contract",
			"naming_series": "NBSIPC-.YYYY./.####",
			"contract_title": f"{prefix}-CT",
			"contract_type": "RRA",
			"customer": customer.name,
			"customer_site": site.name,
			"analyzer_pid": analyzer["item"].name,
			"analyzer_description": "Test analyzer",
			"pricing_worksheet": worksheet.name,
			"start_date": "2026-01-01",
			"end_date": "2027-12-31",
			"total_recovery_target": 12000,
			"breach_threshold": 3,
			"grace_period_days": 30,
			"contract_reagent_lines": [
				{
					"item_code": reagent.name,
					"test_parameter": param["param"].name,
					"contract_price": 150,
					"standard_price": 50,
					"monthly_test_volume": 100,
					"min_monthly_qty": 10,
					"cogs_per_unit": 50,
				}
			],
		}
	).insert()


class TestPlacementSetup(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Instrument Placement Contract")
		super().setUpClass()

	def test_seeders_idempotent(self):
		_seed_all()
		_seed_all()
		for code in ("REVENUE-SHARE-FEE", "SHORTFALL-PENALTY", "Capital Asset"):
			self.assertTrue(frappe.db.exists("Item", code))
			self.assertEqual(frappe.db.count("Item", {"item_code": code}), 1)
		self.assertTrue(frappe.db.exists("Brand", "Others"))
		self.assertTrue(frappe.db.exists("Asset Category", "Equipment"))

	def test_fee_items_invoice_submits(self):
		_seed_all()
		customer = make_customer("_TST-SET1")
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": COMPANY,
				"customer": customer.name,
				"transaction_date": frappe.utils.today(),
				"delivery_date": frappe.utils.today(),
				"items": [
					{"item_code": "REVENUE-SHARE-FEE", "qty": 1, "rate": 100},
					{"item_code": "SHORTFALL-PENALTY", "qty": 1, "rate": 50},
				],
			}
		).insert()
		so.submit()
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": customer.name,
				"posting_date": frappe.utils.today(),
				"items": [
					{
						"item_code": "REVENUE-SHARE-FEE",
						"qty": 1,
						"rate": 100,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
					},
					{
						"item_code": "SHORTFALL-PENALTY",
						"qty": 1,
						"rate": 50,
						"sales_order": so.name,
						"so_detail": so.items[1].name,
					},
				],
			}
		).insert()
		si.submit()
		self.assertEqual(si.docstatus, 1)

	def test_permissions_matrix(self):
		full = {"Instrument Placement Contract", "Analyzer Deployment", "Contract Amendment"}
		for dt in full:
			roles = {p.role for p in frappe.get_meta(dt).permissions}
			self.assertIn("Sales Manager", roles)
			self.assertIn("Accounts Manager", roles)
			self.assertIn("Auditor", roles)
		for dt in ("Instrument Placement Contract", "Monthly Reconciliation"):
			roles = {p.role for p in frappe.get_meta(dt).permissions}
			self.assertIn("Sales User", roles)

	def test_capitalize_requires_serial(self):
		_seed_all()
		analyzer = make_analyzer("_TST-SET2")
		reagent = make_reagent("_TST-SET2R")
		link_reagent_to_spec(analyzer["item"].name, analyzer["param"], reagent)
		customer = make_customer("_TST-SET2")
		ws = make_worksheet("_TST-SET2", analyzer, reagent, analyzer, customer)
		ct = _draft_contract("_TST-SET2", analyzer, reagent, analyzer, customer, make_site("_TST-SET2"), ws)
		with self.assertRaises(frappe.ValidationError):
			ct.create_asset_from_stock(WAREHOUSE, "")
		plain = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_TST-SET2-PLAIN",
				"item_group": "Products",
				"is_stock_item": 1,
				"stock_uom": "Nos",
			}
		).insert()
		ct.analyzer_pid = plain.name
		with self.assertRaises(frappe.ValidationError):
			ct.create_asset_from_stock(WAREHOUSE, "SN-XXX")

	def test_capitalize_redeploy_decommission(self):
		from nbs_customization.controllers.placement.contract import decommission_analyzer

		_seed_all()
		analyzer = make_analyzer("_TST-SET3")
		reagent = make_reagent("_TST-SET3R")
		link_reagent_to_spec(analyzer["item"].name, analyzer["param"], reagent)
		customer = make_customer("_TST-SET3")
		site = make_site("_TST-SET3")
		ws = make_worksheet("_TST-SET3", analyzer, reagent, analyzer, customer)
		serial = make_serial(analyzer["item"].name, WAREHOUSE, "_TST-SET3-SN")
		ct = _draft_contract("_TST-SET3", analyzer, reagent, analyzer, customer, site, ws)
		asset_name = ct.create_asset_from_stock(WAREHOUSE, serial.serial_no)
		frappe.db.set_value("Asset", asset_name, "location", "Field 1")
		ct.submit()

		dep1 = frappe.get_doc(
			{
				"doctype": "Analyzer Deployment",
				"naming_series": "NBSAD-.YYYY./.####",
				"contract": ct.name,
				"asset": asset_name,
				"customer": customer.name,
				"customer_site": site.name,
				"asset_location": "Block 1",
				"asset_storage_location": "Field 1",
				"deployment_date": frappe.utils.today(),
				"deployment_status": "Under Service",
			}
		).insert()
		dep1.deployment_status = "Deployed"
		dep1.save()
		with self.assertRaises(frappe.ValidationError):
			decommission_analyzer(asset_name)
		dep1.deployment_status = "Permanently Retrieved"
		dep1.retrieval_date = frappe.utils.add_days(frappe.utils.today(), 1)
		dep1.save()

		ws2 = make_worksheet("_TST-SET3B", analyzer, reagent, analyzer, customer)
		ct2 = _draft_contract("_TST-SET3B", analyzer, reagent, analyzer, customer, site, ws2)
		ct2.asset = asset_name
		ct2.serial_no = serial.serial_no
		ct2.submit()
		dep2 = frappe.get_doc(
			{
				"doctype": "Analyzer Deployment",
				"naming_series": "NBSAD-.YYYY./.####",
				"contract": ct2.name,
				"asset": asset_name,
				"customer": customer.name,
				"customer_site": site.name,
				"asset_location": "Block 1",
				"asset_storage_location": "Field 1",
				"deployment_date": frappe.utils.add_days(frappe.utils.today(), 2),
				"deployment_status": "Under Service",
			}
		).insert()
		dep2.deployment_status = "Deployed"
		dep2.save()
		self.assertEqual(
			frappe.db.count("Analyzer Deployment", {"asset": asset_name}),
			2,
		)
		dep2.deployment_status = "Permanently Retrieved"
		dep2.retrieval_date = frappe.utils.add_days(frappe.utils.today(), 3)
		dep2.save()
		frappe.db.set_value("Instrument Placement Contract", ct2.name, "contract_status", "Closed")
		decommission_analyzer(asset_name)
		self.assertEqual(frappe.db.get_value("Asset", asset_name, "status"), "Scrapped")

	def test_outright_sale_has_no_contract_side_effects(self):
		analyzer = make_analyzer("_TST-SET4")
		customer = make_customer("_TST-SET4")
		serial = make_serial(analyzer["item"].name, WAREHOUSE, "_TST-SET4-SN")
		bin_qty = (
			frappe.db.get_value(
				"Bin", {"item_code": analyzer["item"].name, "warehouse": WAREHOUSE}, "actual_qty"
			)
			or 0
		)
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": COMPANY,
				"customer": customer.name,
				"transaction_date": "2026-07-10",
				"delivery_date": "2026-07-12",
				"items": [
					{"item_code": analyzer["item"].name, "qty": 1, "rate": 5000, "warehouse": WAREHOUSE}
				],
			}
		).insert()
		so.submit()
		dn = frappe.get_doc(
			{
				"doctype": "Delivery Note",
				"company": COMPANY,
				"customer": customer.name,
				"posting_date": "2026-07-11",
				"items": [
					{
						"item_code": analyzer["item"].name,
						"qty": 1,
						"rate": 5000,
						"warehouse": WAREHOUSE,
						"against_sales_order": so.name,
						"so_detail": so.items[0].name,
						"serial_no": serial.serial_no,
					}
				],
			}
		).insert()
		dn.submit()
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"customer": customer.name,
				"posting_date": "2026-07-11",
				"items": [
					{
						"item_code": analyzer["item"].name,
						"qty": 1,
						"rate": 5000,
						"sales_order": so.name,
						"so_detail": so.items[0].name,
						"delivery_note": dn.name,
						"dn_detail": dn.items[0].name,
					}
				],
			}
		).insert()
		si.submit()
		self.assertEqual(si.docstatus, 1)
		self.assertEqual(frappe.db.get_value("Serial No", serial.serial_no, "status"), "Delivered")
		after = (
			frappe.db.get_value(
				"Bin", {"item_code": analyzer["item"].name, "warehouse": WAREHOUSE}, "actual_qty"
			)
			or 0
		)
		self.assertEqual(after, bin_qty - 1)
		self.assertFalse(frappe.db.exists("Asset", {"custom_serial_no": serial.serial_no}))
