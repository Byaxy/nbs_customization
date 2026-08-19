import frappe

# ─── Selling sidebar items ────────────────────────────────────────────────────

NBS_SELLING_SIDEBAR_ITEMS = [
	{
		"label": "Customer Delivery Note",
		"type": "Link",
		"icon": "file-text",
		"link_to": "Customer Delivery Note",
		"link_type": "DocType",
		"child": 1,
		"indent": 0,
		"collapsible": 1,
		"keep_closed": 0,
		"open_in_new_tab": 0,
	},
	{
		"label": "Promissory Note",
		"type": "Link",
		"icon": "handshake",
		"link_to": "Promissory Note",
		"link_type": "DocType",
		"child": 1,
		"indent": 0,
		"collapsible": 1,
		"keep_closed": 0,
		"open_in_new_tab": 0,
	},
	{
		"label": "Waybill",
		"type": "Link",
		"icon": "truck",
		"link_to": "Delivery Note",
		"link_type": "DocType",
		"child": 1,
		"indent": 0,
		"collapsible": 1,
		"keep_closed": 0,
		"open_in_new_tab": 0,
	},
	{
		"label": "Loan Waybill",
		"type": "Link",
		"icon": "truck-electric",
		"link_to": "Loan Waybill",
		"link_type": "DocType",
		"child": 1,
		"indent": 0,
		"collapsible": 1,
		"keep_closed": 0,
		"open_in_new_tab": 0,
	},
]

NBS_LABELS = [item["label"] for item in NBS_SELLING_SIDEBAR_ITEMS]
NBS_EXPECTED = {item["label"]: item for item in NBS_SELLING_SIDEBAR_ITEMS}


# ─── Accounting / Invoicing sidebar items ─────────────────────────────────────

NBS_EXPENSE_SIDEBAR_ITEMS = [
	{
		"label": "Expenses",
		"type": "Section Break",
		"icon": "badge-dollar-sign",
		"child": 0,
		"indent": 0,
		"collapsible": 1,
		"keep_closed": 1,
		"link_type": "DocType",
		"open_in_new_tab": 0,
	},
	{
		"label": "Expense",
		"type": "Link",
		"icon": "",
		"link_to": "Expense",
		"link_type": "DocType",
		"child": 1,
		"indent": 1,
		"collapsible": 1,
		"keep_closed": 0,
		"open_in_new_tab": 0,
	},
]

NBS_EXPENSE_LABELS = [item["label"] for item in NBS_EXPENSE_SIDEBAR_ITEMS]
NBS_EXPENSE_EXPECTED = {item["label"]: item for item in NBS_EXPENSE_SIDEBAR_ITEMS}

# The anchor — inject after this item in both Accounting and Invoicing
EXPENSE_ANCHOR = "Repost Payment Ledger"

# ─── Daily Income & Expense dashboard link ────────────────────────────────────

NBS_DASHBOARD_SIDEBAR_ITEMS = [
	{
		"label": "Daily Income & Expense",
		"type": "Link",
		"icon": "bar-chart",
		"link_to": "daily_income_expense",
		"link_type": "Page",
		"child": 0,
		"indent": 0,
		"collapsible": 1,
		"keep_closed": 0,
		"open_in_new_tab": 0,
	},
]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _is_correctly_placed(items):
	"""
	Returns True only if all four NBS selling items are present,
	in correct order immediately after 'Sales Invoice'.
	"""
	nbs_rows = [row for row in items if row.label in set(NBS_LABELS)]
	if len(nbs_rows) != len(NBS_LABELS):
		return False

	sales_invoice_idx = next((i for i, row in enumerate(items) if row.label == "Sales Invoice"), None)
	if sales_invoice_idx is None:
		return False

	for j, expected_label in enumerate(NBS_LABELS):
		slot_idx = sales_invoice_idx + 1 + j
		if slot_idx >= len(items):
			return False
		row = items[slot_idx]
		expected = NBS_EXPECTED[expected_label]
		if (
			row.label != expected["label"]
			or row.icon != expected["icon"]
			or row.link_to != expected["link_to"]
			or row.link_type != expected["link_type"]
		):
			return False

	return True


def _is_expense_correctly_placed(items):
	nbs_rows = [row for row in items if row.label in set(NBS_EXPENSE_LABELS)]
	if len(nbs_rows) != len(NBS_EXPENSE_LABELS):
		return False

	anchor_idx = next((i for i, row in enumerate(items) if row.label == EXPENSE_ANCHOR), None)
	if anchor_idx is None:
		return False

	for j, expected_label in enumerate(NBS_EXPENSE_LABELS):
		slot_idx = anchor_idx + 1 + j
		if slot_idx >= len(items):
			return False
		row = items[slot_idx]
		expected = NBS_EXPENSE_EXPECTED[expected_label]

		# Section break rows don't have link_to — only check label and icon
		if expected.get("type") == "Section Break":
			if row.label != expected["label"] or row.icon != expected["icon"]:
				return False
		else:
			if (
				row.label != expected["label"]
				or row.icon != expected["icon"]
				or row.link_to != expected["link_to"]
				or row.link_type != expected["link_type"]
			):
				return False

	return True


def _inject_expense_items(sidebar_name):
	"""
	Injects the Expenses collapsible group after EXPENSE_ANCHOR
	in the given Workspace Sidebar. Idempotent and upgrade-safe.
	"""
	if not frappe.db.exists("Workspace Sidebar", sidebar_name):
		return

	sidebar = frappe.get_doc("Workspace Sidebar", sidebar_name)

	if _is_expense_correctly_placed(sidebar.items):
		return

	# Remove stale NBS expense rows
	label_set = set(NBS_EXPENSE_LABELS)
	sidebar.items = [row for row in sidebar.items if row.label not in label_set]

	# Find insertion point — immediately after anchor
	insert_idx = next(
		(i + 1 for i, row in enumerate(sidebar.items) if row.label == EXPENSE_ANCHOR),
		len(sidebar.items),  # fallback: append at end
	)

	new_items = sidebar.items[:insert_idx]

	for item_data in NBS_EXPENSE_SIDEBAR_ITEMS:
		new_row = frappe.new_doc("Workspace Sidebar Item")
		new_row.update(item_data)
		new_row.parent = sidebar_name
		new_row.parenttype = "Workspace Sidebar"
		new_row.parentfield = "items"
		new_items.append(new_row)

	new_items += sidebar.items[insert_idx:]
	sidebar.items = new_items

	for i, row in enumerate(sidebar.items):
		row.idx = i + 1

	sidebar.flags.ignore_permissions = True
	sidebar.flags.ignore_links = True
	sidebar.save()
	frappe.db.commit()


def _inject_dashboard_item(sidebar_name):
	"""
	Injects the 'Daily Income & Expense' page link into the given
	Workspace Sidebar, right after the NBS Expenses group. Idempotent.
	"""
	if not frappe.db.exists("Workspace Sidebar", sidebar_name):
		return

	sidebar = frappe.get_doc("Workspace Sidebar", sidebar_name)

	if any(row.label == NBS_DASHBOARD_SIDEBAR_ITEMS[0]["label"] for row in sidebar.items):
		return

	sidebar.items = [row for row in sidebar.items if row.label != NBS_DASHBOARD_SIDEBAR_ITEMS[0]["label"]]

	insert_idx = next(
		(i + 1 for i in reversed(range(len(sidebar.items))) if sidebar.items[i].label == "Expense"),
		next(
			(i + 1 for i, row in enumerate(sidebar.items) if row.label == EXPENSE_ANCHOR),
			len(sidebar.items),
		),
	)

	new_row = frappe.new_doc("Workspace Sidebar Item")
	new_row.update(NBS_DASHBOARD_SIDEBAR_ITEMS[0])
	new_row.parent = sidebar_name
	new_row.parenttype = "Workspace Sidebar"
	new_row.parentfield = "items"

	new_items = [*sidebar.items[:insert_idx], new_row, *sidebar.items[insert_idx:]]
	sidebar.items = new_items

	for i, row in enumerate(sidebar.items):
		row.idx = i + 1

	sidebar.flags.ignore_permissions = True
	sidebar.flags.ignore_links = True
	sidebar.save()
	frappe.db.commit()


# ─── after_migrate entry point ────────────────────────────────────────────────


def drop_paying_account_columns():
	"""Drop leftover `paying_account` columns.

	The field was removed from the Expense and Commission Payout doctypes.
	Frappe only drops unique constraints for removed fields, not the columns
	themselves, so drop them here. The guard queries `information_schema`
	directly — `frappe.db.has_column` is unsafe here because table columns
	are cached in Redis and never invalidated on DDL, so it can report a
	stale `True` on later migrates.
	"""
	for doctype in ("Expense", "Commission Payout"):
		exists = frappe.db.sql(
			"SELECT 1 FROM information_schema.COLUMNS "
			"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = 'paying_account'",
			f"tab{doctype}",
		)
		if exists:
			frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `paying_account`")


# ── Cheque clearing setup (:idempotent:) ────────────────────────────────────────


def _find_group(company, options):
	"""Return the first existing group account among `options` for `company`."""
	for name in options:
		if frappe.db.exists("Account", {"company": company, "account_name": name, "is_group": 1}):
			return frappe.db.get_value(
				"Account", {"company": company, "account_name": name, "is_group": 1}, "name"
			)
	return None


def _ensure_account(company, account_name, parent_account, root_type):
	if frappe.db.exists("Account", {"company": company, "account_name": account_name}):
		return frappe.db.get_value("Account", {"company": company, "account_name": account_name}, "name")

	acc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": account_name,
			"parent_account": parent_account,
			"root_type": root_type,
			"is_group": 0,
			"company": company,
			"account_currency": frappe.get_cached_value("Company", company, "default_currency"),
		}
	)
	acc.insert(ignore_permissions=True)
	return acc.name


def _account_for(company, account_name):
	return frappe.db.get_value("Account", {"company": company, "account_name": account_name}, "name")


def _ensure_check_clearing_setup():
	"""
	Idempotent: create the two cheque clearing accounts per company and the
	single 'Check' Mode of Payment wired to them. Clearing accounts carry no
	account_type so they stay out of the standard Bank/Cash account pickers.
	"""
	company_to_accounts = {}
	for company in frappe.get_all("Company", pluck="name"):
		assets = _find_group(company, ["Current Assets", "Assets"])
		liabilities = _find_group(company, ["Current Liabilities", "Liabilities"])
		if not assets or not liabilities:
			continue
		inward = _ensure_account(company, "Cheques in Transit - Inward", assets, "Asset")
		outward = _ensure_account(company, "Cheques in Transit - Outward", liabilities, "Liability")
		company_to_accounts[company] = {"inward": inward, "outward": outward}

	if not company_to_accounts:
		return

	if not frappe.db.exists("Mode of Payment", "Check"):
		mop = frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": "Check", "enabled": 1})
		for company, accounts in company_to_accounts.items():
			mop.append("accounts", {"company": company, "default_account": accounts["inward"]})
		mop.insert(ignore_permissions=True)
	else:
		mop = frappe.get_doc("Mode of Payment", "Check")

	company = next(iter(company_to_accounts))
	accounts = company_to_accounts[company]
	mop.is_check = 1
	mop.clearing_account_inward = accounts["inward"]
	mop.clearing_account_outward = accounts["outward"]
	if not mop.default_clearing_destination:
		mop.default_clearing_destination = frappe.get_cached_value(
			"Company", company, "default_bank_account"
		)
	mop.flags.ignore_permissions = True
	mop.save()


def after_migrate():
	"""
	1. Drop leftover legacy `paying_account` columns.
	2. Inject NBS selling items into the Selling sidebar.
	3. Inject NBS expense group into both Accounting and Invoicing sidebars.
	4. Create cheque clearing accounts + the Check Mode of Payment.
	Idempotent — only writes when a change is actually needed.
	"""

	drop_paying_account_columns()

	# ── Selling sidebar ──────────────────────────────────────────────────────
	if frappe.db.exists("Workspace Sidebar", "Selling"):
		sidebar = frappe.get_doc("Workspace Sidebar", "Selling")

		if not _is_correctly_placed(sidebar.items):
			nbs_label_set = set(NBS_LABELS)
			sidebar.items = [row for row in sidebar.items if row.label not in nbs_label_set]

			insert_idx = next(
				(i + 1 for i, row in enumerate(sidebar.items) if row.label == "Sales Invoice"),
				len(sidebar.items),
			)

			new_items = sidebar.items[:insert_idx]
			for item_data in NBS_SELLING_SIDEBAR_ITEMS:
				new_row = frappe.new_doc("Workspace Sidebar Item")
				new_row.update(item_data)
				new_row.parent = "Selling"
				new_row.parenttype = "Workspace Sidebar"
				new_row.parentfield = "items"
				new_items.append(new_row)

			new_items += sidebar.items[insert_idx:]
			sidebar.items = new_items

			for i, row in enumerate(sidebar.items):
				row.idx = i + 1

			sidebar.flags.ignore_permissions = True
			sidebar.save()
			frappe.db.commit()

	# ── Accounting sidebar ───────────────────────────────────────────────────
	_inject_expense_items("Accounting")

	# ── Invoicing sidebar (v16 experimental) ────────────────────────────────
	_inject_expense_items("Invoicing")

	# ── Daily Income & Expense dashboard link ────────────────────────────────
	_inject_dashboard_item("Accounting")
	_inject_dashboard_item("Invoicing")

	# ── Cheque clearing accounts + Check mode of payment ────────────────────
	_ensure_check_clearing_setup()

	# ── Placement Fee Items (PAUSED — revenue share / placement WIP) ─────
	# Re-enable when the placement module is ready for production.
	# _ensure_brand_others()
	# create_revenue_share_fee_item()
	# create_shortfall_penalty_item()
	# create_nbs_capital_asset_item()


# ── PAUSED: revenue share / placement seeders — re-enable with the module ─────
# def _ensure_brand_others():
# 	"""Create 'Others' brand if absent."""
# 	if not frappe.db.exists("Brand", "Others"):
# 		frappe.get_doc({"doctype": "Brand", "brand": "Others"}).insert(ignore_permissions=True)
#
#
# def create_revenue_share_fee_item():
# 	"""Create the Revenue Share Fee non-stock item if absent."""
# 	if not frappe.db.exists("Item", "REVENUE-SHARE-FEE"):
# 		item = frappe.get_doc(
# 			{
# 				"doctype": "Item",
# 				"item_code": "REVENUE-SHARE-FEE",
# 				"item_name": "Revenue Share Fee",
# 				"description": "Revenue Share Fee",
# 				"item_group": "Services",
# 				"is_stock_item": 0,
# 				"brand": "Others",
# 			}
# 		)
# 		item.insert(ignore_permissions=True)
#
#
# def create_shortfall_penalty_item():
# 	"""Create the Shortfall Penalty non-stock item if absent."""
# 	if not frappe.db.exists("Item", "SHORTFALL-PENALTY"):
# 		item = frappe.get_doc(
# 			{
# 				"doctype": "Item",
# 				"item_code": "SHORTFALL-PENALTY",
# 				"item_name": "Shortfall Penalty",
# 				"description": "Shortfall Penalty",
# 				"item_group": "Services",
# 				"is_stock_item": 0,
# 				"brand": "Others",
# 			}
# 		)
# 		item.insert(ignore_permissions=True)
#
#
# def create_nbs_capital_asset_item():
# 	"""Create the shared capital asset fixed-asset item if absent."""
# 	if not frappe.db.exists("Item", "Capital Asset"):
# 		item = frappe.get_doc(
# 			{
# 				"doctype": "Item",
# 				"item_code": "Capital Asset",
# 				"item_name": "Capital Asset",
# 				"description": "Generic capital asset item for capitalized placement analyzers.",
# 				"item_group": "Products",
# 				"is_fixed_asset": 1,
# 				"asset_category": "Equipment",
# 				"is_stock_item": 0,
# 				"brand": "Others",
# 			}
# 		)
# 		item.insert(ignore_permissions=True)
