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


# ─── Expense paying account backfill ─────────────────────────────────────────


def backfill_expense_paid_from():
	"""Copy legacy `paying_account` values into `paid_from` for existing Expense records."""
	_backfill_paying_account("Expense")


def backfill_commission_payout_paid_from():
	"""Copy legacy `paying_account` values into `paid_from` for existing Commission Payout records."""
	_backfill_paying_account("Commission Payout")


def _backfill_paying_account(doctype):
	"""Shared, idempotent data migration for legacy `paying_account` fields.

	Shipped ahead of the `paying_account` field removal. Runs on every migrate
	until the column is dropped, then self-disables via `has_column`. Copies
	`paying_account` → `paid_from` and reverse-looks-up `mode_of_payment` from a
	matching Mode of Payment Account (company + default_account) when exactly one
	exists.
	"""
	if not frappe.db.has_column(doctype, "paying_account"):
		return

	table = f"tab{doctype}"

	frappe.db.sql(
		f"""
        UPDATE `{table}`
        SET paid_from = paying_account
        WHERE paid_from IS NULL AND paying_account IS NOT NULL AND paying_account != ''
        """
	)

	frappe.db.sql(
		f"""
        UPDATE `{table}` e
        LEFT JOIN (
            SELECT mpa.company, mpa.default_account, mpa.parent
            FROM `tabMode of Payment Account` mpa
            GROUP BY mpa.company, mpa.default_account
            HAVING COUNT(DISTINCT mpa.parent) = 1
        ) cm ON cm.company = e.company AND cm.default_account = e.paying_account
        LEFT JOIN (
            SELECT mpa.default_account, mpa.parent
            FROM `tabMode of Payment Account` mpa
            GROUP BY mpa.default_account
            HAVING COUNT(DISTINCT mpa.parent) = 1
        ) am ON am.default_account = e.paying_account
        SET e.mode_of_payment = COALESCE(cm.parent, am.parent)
        WHERE e.mode_of_payment IS NULL
            AND e.paying_account IS NOT NULL
            AND e.paying_account != ''
        """
	)


# ─── after_migrate entry point ────────────────────────────────────────────────


def after_migrate():
	"""
	0. Backfill legacy `paying_account` → `paid_from` on Expense and Commission Payout.
	1. Inject NBS selling items into the Selling sidebar.
	2. Inject NBS expense group into both Accounting and Invoicing sidebars.
	Idempotent — only writes when a change is actually needed.
	"""

	# ── Expense / Commission Payout paying account backfill ────────────────
	backfill_expense_paid_from()
	backfill_commission_payout_paid_from()

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
