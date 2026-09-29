# Shared builders for placement TDD backfill (Phase 01).
# All names take a caller prefix (e.g. "_TST-REC"); tests roll back, no cleanup.

import frappe

COMPANY = "NORTHLAND BIOMEDICAL SOLUTIONS"
WAREHOUSE = "Stores - NBS"
STORAGE_LOCATION = "Field 1"
SITE_LOCATION = "Block 1"
BANK_ACCOUNT = "ECOBANK Current Account - USD - NBS"


def skip_test_record_bootstrap(doctype):
	# Fixtures here are self-built: mark the doctype loaded so
	# IntegrationTestCase skips the ERPNext test-record bootstrap, whose
	# import-time master-data insert collides with live-site data.
	frappe.local.test_objects[doctype] = []


def make_analyzer(prefix):
	# Serialized stock analyzer + type + param + spec with one test method.
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": f"{prefix}-AN",
			"item_group": "Products",
			"is_stock_item": 1,
			"has_serial_no": 1,
			"stock_uom": "Nos",
		}
	).insert(ignore_if_duplicate=True)
	atype = frappe.get_doc({"doctype": "Analyzer Type", "title": f"{prefix}-AT"}).insert(
		ignore_if_duplicate=True
	)
	param = frappe.get_doc(
		{
			"doctype": "Test Parameter",
			"parameter_name": f"{prefix}-PM",
			"parameter_code": prefix[-4:],
		}
	).insert(ignore_if_duplicate=True)
	return {"item": item, "atype": atype, "param": param}


def make_reagent(prefix, role="Test Reagent", cogs=50, tpp=100):
	# Stock reagent/consumable + spec; caller links it into the analyzer spec.
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": f"{prefix}-RG",
			"item_group": "Products",
			"is_stock_item": 1,
			"stock_uom": "Nos",
			"item_defaults": [{"company": COMPANY, "default_warehouse": WAREHOUSE}],
		}
	).insert(ignore_if_duplicate=True)
	frappe.get_doc(
		{
			"doctype": "Reagent Specification",
			"item": item.name,
			"reagent_role": role,
			"default_cogs_per_pack": cogs,
			"default_tests_per_pack": tpp,
		}
	).insert(ignore_if_duplicate=True)
	return item


def link_reagent_to_spec(analyzer_item, param, reagent_item):
	# Register reagent as valid for the analyzer (drives placement validation).
	spec_name = frappe.db.get_value("Instrument Specification", {"item": analyzer_item}, "name")
	if spec_name:
		spec = frappe.get_doc("Instrument Specification", spec_name)
	else:
		atype = frappe.db.get_value("Analyzer Type", {}, "name")
		spec = frappe.get_doc(
			{
				"doctype": "Instrument Specification",
				"item": analyzer_item,
				"analyzer_type": atype,
				"supported_test_methods": [],
			}
		).insert(ignore_if_duplicate=True)
	spec.append(
		"supported_test_methods",
		{
			"test_parameter": param if isinstance(param, str) else param.name,
			"required_reagent": reagent_item if isinstance(reagent_item, str) else reagent_item.name,
		},
	)
	spec.save(ignore_permissions=True)
	return spec


def make_customer(prefix):
	return frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"{prefix}-CUST",
			"customer_type": "Company",
		}
	).insert(ignore_if_duplicate=True)


def make_site(prefix):
	return frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": f"{prefix}-SITE",
			"address_type": "Office",
			"address_line1": "1 Test St",
			"city": "Monrovia",
			"country": "Liberia",
		}
	).insert(ignore_if_duplicate=True)


def ensure_stock(item_name, qty=50, rate=50):
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": COMPANY,
			"to_warehouse": WAREHOUSE,
			"items": [
				{
					"item_code": item_name,
					"qty": qty,
					"transfer_qty": qty,
					"uom": "Nos",
					"basic_rate": rate,
				}
			],
		}
	).insert()
	se.submit()
	return se


def make_serial(analyzer_item, warehouse, serial_no, rate=5000):
	# Real Serial No via stock receipt (ERPNext tracks it Active; see Phase 02
	# note on create_asset_from_stock expecting "In Store").
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": COMPANY,
			"to_warehouse": warehouse,
			"items": [
				{
					"item_code": analyzer_item,
					"qty": 1,
					"transfer_qty": 1,
					"uom": "Nos",
					"basic_rate": rate,
					"use_serial_batch_fields": 1,
					"serial_no": serial_no,
				}
			],
		}
	).insert()
	se.submit()
	return frappe.get_doc("Serial No", serial_no)
