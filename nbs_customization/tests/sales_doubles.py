# Test doubles for erpnext's SI/PI test helpers.
# Importing erpnext.*.test_* modules triggers their import-time master-data
# bootstrap, which collides with live-site data — these builders create the
# same documents directly via frappe.get_doc. Values mirror the erpnext
# defaults the suites assert against (SI 100x1, PI 5x50).

import frappe

COMPANY = "_Test Company"


def _pick(doctype, name, **fallback_filters):
	if frappe.db.exists(doctype, name):
		return name
	return frappe.db.get_value(doctype, fallback_filters, "name")


def _ensure(doctype, name, defaults):
	if frappe.db.exists(doctype, name):
		return name
	doc = frappe.get_doc({"doctype": doctype, "name": name, **defaults})
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_test_item(name="_Test Item"):
	return _ensure(
		"Item",
		name,
		{
			"item_code": name,
			"item_name": name,
			"item_group": "All Item Groups",
			"is_stock_item": 1,
			"stock_uom": "Nos",
		},
	)


def ensure_test_supplier():
	# Supplier autoname reads the global supp_master_name default (Naming Series
	# on this site) — flip it inside the test transaction (rolled back) so the
	# literal "_Test Supplier" can exist.
	if frappe.db.exists("Supplier", "_Test Supplier"):
		return "_Test Supplier"
	previous = frappe.defaults.get_global_default("supp_master_name")
	try:
		frappe.defaults.set_global_default("supp_master_name", "Supplier Name")
		doc = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "_Test Supplier",
				"supplier_group": "All Supplier Groups",
				"supplier_type": "Company",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
	finally:
		if previous:
			frappe.defaults.set_global_default("supp_master_name", previous)


def ensure_mop_default(mode_of_payment, company, account):
	# Prod locks paid_from to the MoP default — ensure it in-test (rolled back).
	doc = frappe.get_doc("Mode of Payment", mode_of_payment)
	if not any(r.company == company and r.default_account == account for r in doc.accounts):
		if not any(r.company == company for r in doc.accounts):
			doc.append("accounts", {"company": company, "default_account": account})
			doc.save(ignore_permissions=True)


def make_test_sales_invoice(*, posting_date, rate=100, qty=1, customer="_Test Customer"):
	# Backdated posting needs an explicit timestamp (core resets it otherwise).
	# Site mandates SO links on SI items, so every double ships with its order.
	item_code = ensure_test_item()
	uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
	customer = _ensure(
		"Customer",
		customer,
		{
			"customer_name": customer,
			"customer_type": "Company",
			"customer_group": _pick("Customer Group", "Commercial")
			or frappe.db.get_all("Customer Group", pluck="name")[0],
			"territory": _pick("Territory", "Rest of the World")
			or frappe.db.get_all("Territory", pluck="name")[0],
		},
	)
	so = frappe.new_doc("Sales Order")
	so.company = COMPANY
	so.customer = customer
	so.transaction_date = posting_date
	so.delivery_date = posting_date
	so.currency = frappe.db.get_value("Company", COMPANY, "default_currency") or "USD"
	so.conversion_rate = 1
	so.append(
		"items",
		{
			"item_code": item_code,
			"qty": qty,
			"uom": uom,
			"stock_uom": uom,
			"conversion_factor": 1,
			"rate": rate,
			"warehouse": _pick("Warehouse", "_Test Warehouse - _TC", company=COMPANY, is_group=0),
		},
	)
	so.insert(ignore_permissions=True)
	so.submit()
	si = frappe.new_doc("Sales Invoice")
	si.set_posting_time = 1
	si.posting_date = posting_date
	si.company = COMPANY
	si.customer = customer
	si.debit_to = _pick("Account", "Debtors - _TC", company=COMPANY, account_type="Receivable")
	si.currency = frappe.db.get_value("Company", COMPANY, "default_currency") or "USD"
	si.conversion_rate = 1
	si.append(
		"items",
		{
			"item_code": item_code,
			"qty": qty,
			"uom": uom,
			"stock_uom": uom,
			"rate": rate,
			"price_list_rate": rate,
			"sales_order": so.name,
			"so_detail": so.items[0].name,
			"income_account": _pick(
				"Account", "Sales - _TC", company=COMPANY, root_type="Income", is_group=0
			),
			"expense_account": _pick(
				"Account",
				"Cost of Goods Sold - _TC",
				company=COMPANY,
				root_type="Expense",
				is_group=0,
			),
			"cost_center": _pick("Cost Center", "_Test Cost Center - _TC", company=COMPANY, is_group=0),
			"conversion_factor": 1,
		},
	)
	si.insert(ignore_permissions=True)
	si.submit()
	return si


def make_test_purchase_invoice():
	pi = frappe.new_doc("Purchase Invoice")
	pi.posting_date = frappe.utils.today()
	pi.set_posting_time = 1
	pi.company = COMPANY
	pi.supplier = ensure_test_supplier()
	pi.currency = "INR"
	pi.conversion_rate = 1
	pi.append(
		"items",
		{
			"item_code": ensure_test_item(),
			"warehouse": _pick("Warehouse", "_Test Warehouse - _TC", company=COMPANY, is_group=0),
			"qty": 5,
			"rate": 50,
			"price_list_rate": 50,
			"expense_account": _pick(
				"Account",
				"Cost of Goods Sold - _TC",
				company=COMPANY,
				root_type="Expense",
				is_group=0,
			),
			"conversion_factor": 1,
			"stock_uom": "Nos",
			"cost_center": _pick("Cost Center", "_Test Cost Center - _TC", company=COMPANY, is_group=0),
		},
	)
	pi.insert(ignore_permissions=True)
	pi.submit()
	return pi
