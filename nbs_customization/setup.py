import frappe

# ─── Module sidebar placements (v16.50 Sidebar / Custom Sidebar) ───────────────
#
# The desk runs on the Apps screen: each module resolves its sidebar from the
# module's shipped Sidebar plus the site-wide Custom Sidebar layer ("For
# everyone"). Items below are interleaved flat with the shipped entries — no
# NBS sections — so they read like native module content.
#
# Each entry is (label, link_to, link_type, icon, after) where `after` names
# the label the item follows. Anchors chain onto earlier spec items where
# possible, so placements survive upstream renames of base rows; a missing
# anchor falls back to the end of the list.
#
# Note: the "Waybill" row intentionally shares its identity columns with the
# base "Delivery Note" link (identity ignores the label), so it relabels that
# entry rather than adding a second one.

NBS_SIDEBAR_PLACEMENTS = {
	"Selling": [
		("Customer Delivery Note", "Customer Delivery Note", "DocType", "file-text", "Sales Invoice"),
		("Promissory Note", "Promissory Note", "DocType", "notebook-pen", "Customer Delivery Note"),
		("Waybill", "Delivery Note", "DocType", "truck", "Promissory Note"),
		("Loan Waybill", "Loan Waybill", "DocType", "truck-electric", "Waybill"),
		("Sales Commission", "Sales Commission", "DocType", "badge-percent", "Loan Waybill"),
		("Commission Payout", "Commission Payout", "DocType", "banknote-check", "Sales Commission"),
		(
			"Item Pricing Quotation Batch",
			"Item Pricing Quotation Batch",
			"DocType",
			"clipboard-list",
			"Pricing Rule",
		),
		(
			"Instrument Pricing Worksheet",
			"Instrument Pricing Worksheet",
			"DocType",
			"sheet",
			"Item Pricing Quotation Batch",
		),
	],
	"Buying": [
		("Inbound Shipment", "Inbound Shipment", "DocType", "package-check", "Purchase Invoice"),
		("Carrier", "Carrier", "DocType", "truck", "Inbound Shipment"),
	],
	"Stock": [
		("Item Pricing Settings", "Item Pricing Settings", "DocType", "settings", "Delivery Note"),
		("Item Type", "Item Type", "DocType", "package", "Unit of Measure (UOM)"),
		("Instrument Specification", "Instrument Specification", "DocType", "clipboard-check", "Item Type"),
		(
			"Reagent Specification",
			"Reagent Specification",
			"DocType",
			"file-text",
			"Instrument Specification",
		),
		("Test Panel Group", "Test Panel Group", "DocType", "table", "Reagent Specification"),
		("Test Parameter", "Test Parameter", "DocType", "sliders-horizontal", "Test Panel Group"),
	],
	"Assets": [
		(
			"Instrument Placement Contract",
			"Instrument Placement Contract",
			"DocType",
			"file-text",
			"Asset Movement",
		),
		(
			"Contract Amendment",
			"Contract Amendment",
			"DocType",
			"notebook-pen",
			"Instrument Placement Contract",
		),
		("Analyzer Deployment", "Analyzer Deployment", "DocType", "monitor", "Contract Amendment"),
		(
			"Ownership Transfer Request",
			"Ownership Transfer Request",
			"DocType",
			"arrow-left-right",
			"Analyzer Deployment",
		),
		("Repossession Request", "Repossession Request", "DocType", "move", "Ownership Transfer Request"),
		("Analyzer Type", "Analyzer Type", "DocType", "package", "Location"),
	],
	"Accounts": [
		("Expense", "Expense", "DocType", "receipt-text", "Journal Entry"),
		("Receipt", "Receipt", "DocType", "banknote-check", "Expense"),
		("Monthly Reconciliation", "Monthly Reconciliation", "DocType", "clipboard-check", "Receipt"),
		(
			"Revenue Share Statement",
			"Revenue Share Statement",
			"DocType",
			"piggy-bank",
			"Monthly Reconciliation",
		),
		("Daily Income & Expense", "daily_income_expense", "Page", "bar-chart", "Revenue Share Statement"),
		("Commission Payout", "Commission Payout", "DocType", "banknote-check", "Payment Entry"),
		("Expense Tax", "Expense Tax", "DocType", "scale", "Tax Withholding Category"),
		("Expense Category", "Expense Category", "DocType", "table", "Currency Exchange"),
	],
}

# Labels of removed items, kept so their rows are cleaned from site layers on
# the next migrate. Add here (never delete) whenever a spec item is retired.
NBS_RETIRED_LABELS = {"Commission Recipient"}

# Every label this app owns per module, including retired rows and section
# headers, so renames/removals clean up after themselves. Admin/user rows are
# never touched.
NBS_MANAGED_LABELS = {
	module: {label for label, _to, _type, _icon, _after in items}
	| {"NBS Sales", "NBS Procurement", "NBS Lab & Pricing", "NBS Placements", "NBS Finance"}
	| NBS_RETIRED_LABELS
	for module, items in NBS_SIDEBAR_PLACEMENTS.items()
}


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _site_layer_name(module):
	return frappe.db.exists("Custom Sidebar", {"module": module, "user": ["in", ["", None]]})


def _layer_has_foreign_rows(module, managed):
	"""True when the site layer holds admin-added rows we must not reorder."""
	name = _site_layer_name(module)
	if not name:
		return False
	layer = frappe.get_doc("Custom Sidebar", name)
	return any(row.added and row.label not in managed for row in layer.sidebar_items)


def _ensure_site_layer(module):
	"""Idempotently interleave this app's items into the module's site layer.

	Two modes: when the site layer holds admin-added rows, only missing spec
	rows are appended and stale managed rows dropped (never reorder). Otherwise
	the layer is rebuilt to the target arrangement — base order with spec rows
	inserted after their anchors — reusing existing reference rows verbatim so
	label/icon/hidden overrides survive. Per-user layers are never touched.
	"""
	from frappe.desk.doctype.custom_sidebar.custom_sidebar import add_site_sidebar_item

	spec = NBS_SIDEBAR_PLACEMENTS[module]
	managed = NBS_MANAGED_LABELS[module]

	if _layer_has_foreign_rows(module, managed):
		_drop_stale_managed_rows(module, managed, {label for label, *_ in spec})
		_append_missing_spec_rows(module, spec)
		return

	items = _build_target_arrangement(module, spec)
	_rebuild_site_layer(module, items)


def _base_sidebar_rows(module):
	"""Ordered base rows for `module` from its shipped Sidebar doc (may be empty)."""
	if not frappe.db.exists("Sidebar", module):
		return []
	return sorted(frappe.get_doc("Sidebar", module).items, key=lambda r: r.idx or 0)


def _build_target_arrangement(module, spec):
	"""Return the full ordered arrangement: base rows with spec rows inserted.

	Each entry is a dict in layer-row shape: base rows as identity references,
	spec rows as `added: 1` bodies inheriting the anchor's section flags.
	"""
	from frappe.desk.doctype.sidebar.sidebar import LINKED_IDENTITY_FIELDS, unlinked_key

	sequence = []  # list of ("base", row) | ("spec", item)
	placed_labels = {}
	placed_flags = {}
	for row in _base_sidebar_rows(module):
		sequence.append(("base", row))
		placed_labels[row.label] = row
		placed_flags[row.label] = (row.get("child") or 0, row.get("indent") or 0)

	for label, link_to, link_type, icon, after in spec:
		anchor = placed_labels.get(after)
		entry = ("spec", (label, link_to, link_type, icon))
		if anchor is None:
			sequence.append(entry)  # missing anchor (upstream rename) → end
			placed_flags[label] = (0, 0)
		else:
			idx = next(i for i, (_kind, row) in enumerate(sequence) if _row_label(row) == after)
			sequence.insert(idx + 1, entry)
			placed_flags[label] = placed_flags.get(after, (0, 0))
		placed_labels[label] = entry[1]

	arranged = []
	for kind, row in sequence:
		if kind == "base":
			ref = {field: row.get(field) for field in (*LINKED_IDENTITY_FIELDS, "key", "hidden", "child")}
			if not row.get("link_to") and not row.get("url"):
				ref["key"] = row.get("key") or unlinked_key(
					{"type": row.get("type"), "label": row.get("label")}
				)
			arranged.append(ref)
			continue
		label, link_to, link_type, icon = row
		child, indent = placed_flags.get(label, (0, 0))
		arranged.append(
			{
				"type": "Link",
				"label": label,
				"link_to": link_to,
				"link_type": link_type,
				"icon": icon,
				"child": child,
				"indent": indent,
				"collapsible": 0,
				"keep_closed": 0,
				"open_in_new_tab": 0,
				"added": 1,
			}
		)
	return arranged


def _row_label(row):
	return row.label if hasattr(row, "label") else row[0]


def _rebuild_site_layer(module, items):
	"""Replace the site layer with `items` via the editor's write path.

	Existing reference rows are reused verbatim where they name the same base
	item, so admin label/icon/hidden overrides survive the rebuild.
	"""
	from frappe.desk.doctype.custom_sidebar.custom_sidebar import _save_customization
	from frappe.desk.doctype.sidebar.sidebar import item_key

	name = _site_layer_name(module)
	by_key = {}
	if name:
		for row in frappe.get_doc("Custom Sidebar", name).sidebar_items:
			if not row.added:
				by_key[item_key(row)] = row

	merged = []
	for entry in items:
		if entry.get("added"):
			merged.append(entry)
			continue
		merged.append(by_key.get(item_key(entry), entry))

	_save_customization(module, merged, user=None)


def _append_missing_spec_rows(module, spec):
	"""Append spec rows absent from the layer (conservative mode)."""
	from frappe.desk.doctype.custom_sidebar.custom_sidebar import add_site_sidebar_item

	name = _site_layer_name(module)
	present = set()
	if name:
		present = {row.label for row in frappe.get_doc("Custom Sidebar", name).sidebar_items}
	for label, link_to, link_type, icon, _after in spec:
		if label in present:
			continue
		add_site_sidebar_item(
			module,
			{
				"type": "Link",
				"label": label,
				"link_to": link_to,
				"link_type": link_type,
				"icon": icon,
				"child": 0,
				"indent": 0,
				"collapsible": 0,
				"keep_closed": 0,
				"open_in_new_tab": 0,
			},
		)


def _drop_stale_managed_rows(module, managed, specified_labels):
	"""Remove managed rows that are no longer specified. Foreign rows stay."""
	name = _site_layer_name(module)
	if not name:
		return
	layer = frappe.get_doc("Custom Sidebar", name)
	kept = [row for row in layer.sidebar_items if row.label not in managed or row.label in specified_labels]
	if len(kept) == len(layer.sidebar_items):
		return
	layer.sidebar_items = kept
	for i, row in enumerate(layer.sidebar_items):
		row.idx = i + 1
	layer.flags.ignore_permissions = True
	layer.save()
	frappe.db.commit()


def _sync_nbs_sidebars():
	"""Sync every NBS module placement. Idempotent and upgrade-safe."""
	for module in NBS_SIDEBAR_PLACEMENTS:
		if frappe.db.exists("Module Def", module):
			_ensure_site_layer(module)
	frappe.db.commit()


# ─── Dock rail titles, hides & Setup gating (v16.50 Dock) ────────────────────
#
# Dock rail labels render the stored row `title`, which never passes through
# __(), so Translation records cannot rename dock entries. Titles below are
# sourced from this site's `en` Translation records (stripped) and written as
# title overrides into the erpnext app's site dock layer. These are
# single-language renames: they do not switch per user language.

NBS_DOCK_TITLE_SOURCES = {"Selling", "Buying", "Stock"}
NBS_DOCK_HIDDEN_MODULES = {"Manufacturing", "Quality", "Projects"}
NBS_DOCK_APP = "erpnext"


def _dock_title_overrides():
	"""Map dock entry link_to → title from the site language's translations."""
	site_lang = frappe.db.get_single_value("System Settings", "language") or "en"
	rows = frappe.get_all(
		"Translation",
		filters={"language": site_lang, "source_text": ["in", sorted(NBS_DOCK_TITLE_SOURCES)]},
		fields=["source_text", "translated_text"],
	)
	return {r.source_text: r.translated_text.strip() for r in rows if (r.translated_text or "").strip()}


def _sync_dock_titles_and_hides():
	"""Idempotently apply title overrides + hides to the erpnext site dock layer.

	The site layer (standard=0) is distinct from the shipped standard doc: it
	merges over it at resolve time. When no site layer exists yet it is seeded
	from the standard rows, so nothing upstream is dropped.
	"""
	from frappe.desk.doctype.dock.dock import _save_layer, get_dock

	layer = get_dock(NBS_DOCK_APP, user=None)
	if layer is None:
		standard = get_dock(NBS_DOCK_APP, standard=1)
		if standard is None:
			return
		source = standard.items
	else:
		source = layer.items
	titles = _dock_title_overrides()
	changed = layer is None
	items = []
	for row in source:
		entry = {
			"link_type": row.link_type,
			"link_to": row.link_to,
			"url": row.url,
			"icon": row.icon,
			"title": row.title,
			"hidden": row.hidden,
		}
		if row.link_type == "Sidebar" and row.link_to in titles and row.title != titles[row.link_to]:
			entry["title"] = titles[row.link_to]
			changed = True
		if row.link_type == "Sidebar" and row.link_to in NBS_DOCK_HIDDEN_MODULES and not row.hidden:
			entry["hidden"] = 1
			changed = True
		items.append(entry)
	if not changed:
		_assert_dock_titles(titles)
		return
	_save_layer(NBS_DOCK_APP, items, user=None, require_visible=False)
	_assert_dock_titles(titles)


def _assert_dock_titles(titles):
	"""Re-assert title overrides with a direct write.

	The editor write path blanks any title equal to `_(base title)` as merely
	echoed back — which also swallows an override identical to a Translation
	record. A direct save has no such narrowing, so overrides stick.
	"""
	if not titles:
		return
	name = frappe.db.exists("Dock", {"app": NBS_DOCK_APP, "user": ["in", ["", None]], "standard": 0})
	if not name:
		return
	layer = frappe.get_doc("Dock", name)
	dirty = False
	for row in layer.items:
		if row.link_to in titles and row.title != titles[row.link_to]:
			row.title = titles[row.link_to]
			dirty = True
	if not dirty:
		return
	layer.flags.ignore_permissions = True
	layer.save()


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
	existing = frappe.db.get_value("Account", {"company": company, "account_name": account_name}, "name")
	if existing:
		if frappe.db.get_value("Account", existing, "parent_account") != parent_account:
			acc = frappe.get_doc("Account", existing)
			acc.parent_account = parent_account
			acc.flags.ignore_permissions = True
			acc.save()
		return existing

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


def _receivable_payable_groups(company):
	"""Return the (receivable, payable) group account names for `company`.

	Resolves the group accounts from the company's default receivable/payable
	accounts (their parents), falling back to the standard chart names.
	"""
	receivable = payable = None
	default_receivable = frappe.get_cached_value("Company", company, "default_receivable_account")
	default_payable = frappe.get_cached_value("Company", company, "default_payable_account")
	if default_receivable:
		receivable = frappe.db.get_value("Account", default_receivable, "parent_account")
	if default_payable:
		payable = frappe.db.get_value("Account", default_payable, "parent_account")
	receivable = receivable or _find_group(company, ["Accounts Receivable", "Debtors"])
	payable = payable or _find_group(company, ["Accounts Payable", "Creditors"])
	return receivable, payable


def _ensure_check_clearing_setup():
	"""
	Idempotent: create the two cheque clearing accounts per company and the
	single 'Check' Mode of Payment wired to them. Clearing accounts carry no
	account_type so they stay out of the standard Bank/Cash account pickers.
	The inward (asset) account nests under Accounts Receivable and the outward
	(liability) account under Accounts Payable.
	"""
	company_to_accounts = {}
	for company in frappe.get_all("Company", pluck="name"):
		receivable, payable = _receivable_payable_groups(company)
		if not receivable or not payable:
			receivable = receivable or _find_group(company, ["Current Assets", "Assets"])
			payable = payable or _find_group(company, ["Current Liabilities", "Liabilities"])
		if not receivable or not payable:
			continue
		inward = _ensure_account(company, "Cheques in Transit - Inward", receivable, "Asset")
		outward = _ensure_account(company, "Cheques in Transit - Outward", payable, "Liability")
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
		mop.default_clearing_destination = frappe.get_cached_value("Company", company, "default_bank_account")
	mop.flags.ignore_permissions = True
	mop.save()


FIXED_TIER_PRICE_LISTS = [
	("Selling - Basic", "GHS"),
	("Selling - 15%", "GHS"),
	("Selling - 30%", "GHS"),
	("Selling - 45%", "GHS"),
	("Selling - Commission", "GHS"),
	("Selling - Commission (Tax)", "GHS"),
]


def _ensure_tier_price_lists():
	"""
	Idempotent: ensure 6 fixed tier Price Lists. Standard Selling is ERPNext standard — not created here.
	Optional target Price Lists (e.g. Selling - 20%) are user-created when needed.
	"""
	candidates = FIXED_TIER_PRICE_LISTS
	# Use default company currency if present; fallback to GHS
	default_company = frappe.db.get_single_value("Global Defaults", "default_company")
	company_ccy = (
		frappe.get_cached_value("Company", default_company, "default_currency") if default_company else None
	)
	for name, fallback_ccy in candidates:
		if frappe.db.exists("Price List", name):
			continue
		currency = company_ccy or fallback_ccy
		# Validate currency exists
		if not frappe.db.exists("Currency", currency):
			currency = fallback_ccy
		try:
			pl = frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": name,
					"currency": currency,
					"selling": 1,
					"buying": 0,
					"enabled": 1,
				}
			)
			pl.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"ensure_tier_price_lists failed for {name}")


def after_migrate():
	"""
	1. Drop leftover legacy `paying_account` columns.
	2. Interleave NBS items flat into the site-wide sidebar layers
	   (Selling, Buying, Stock, Assets, Accounts).
	3. Rename dock entries + hide unused modules.
	4. Create cheque clearing accounts + the Check Mode of Payment.
	5. Ensure pricing tier Price Lists (Standard Selling = 30% reuse).
	6. Seed placement billing/capital items (Others brand, fee items, Equipment category).
	7. Seed one `{abbr} - Store` Location per company for placement assets.
	8. Seed CPT/RRA/RLO Contract Templates.
	Idempotent — only writes when a change is actually needed.
	"""

	drop_paying_account_columns()

	# ── NBS module sidebar sections (v16.50 site layers) ────────────────────
	_sync_nbs_sidebars()

	# ── Dock titles/hides ────────────────────────────────────────────────────
	_sync_dock_titles_and_hides()

	# ── Cheque clearing accounts + Check mode of payment ────────────────────
	_ensure_check_clearing_setup()

	# ── Pricing tier Price Lists (Standard Selling = 30% reuse) ──────────────
	_ensure_tier_price_lists()

	# ── Placement billing + capital items ────────────────────────────────────
	_ensure_brand_others()
	create_revenue_share_fee_item()
	create_shortfall_penalty_item()
	create_nbs_capital_asset_item()

	# ── Company store Locations for placement assets ───────────────────────
	_ensure_company_store_locations()

	# ── Placement Contract Templates (CPT/RRA/RLO) ─────────────────────────
	from nbs_customization.placement_contract_templates import ensure_placement_contract_templates

	ensure_placement_contract_templates()


def _ensure_brand_others():
	"""Create 'Others' brand if absent."""
	if not frappe.db.exists("Brand", "Others"):
		frappe.get_doc({"doctype": "Brand", "brand": "Others"}).insert(ignore_permissions=True)


def _ensure_equipment_category():
	"""Create Asset Category 'Equipment' with straight-line defaults if absent."""
	if frappe.db.exists("Asset Category", "Equipment"):
		_backfill_equipment_accounts()
		return
	frappe.get_doc(
		{
			"doctype": "Asset Category",
			"asset_category_name": "Equipment",
			"accounts": _equipment_account_rows(),
			"finance_books": [
				{
					"depreciation_method": "Straight Line",
					"frequency_of_depreciation": 12,
					"total_number_of_depreciations": 60,
				}
			],
		}
	).insert(ignore_permissions=True)


def _equipment_account_rows():
	"""One accounts row per company with standard fixed-asset accounts."""
	rows = []
	for name in frappe.db.get_all("Company", pluck="name"):
		abbr = frappe.db.get_value("Company", name, "abbr")
		fixed = frappe.db.get_value("Account", f"Capital Equipment - {abbr}", "name") or frappe.db.get_value(
			"Account", {"company": name, "account_type": "Fixed Asset", "is_group": 0}, "name"
		)
		accum = frappe.db.get_value(
			"Account", {"company": name, "account_type": "Accumulated Depreciation", "is_group": 0}, "name"
		)
		expense = frappe.db.get_value(
			"Account", {"company": name, "account_type": "Depreciation", "is_group": 0}, "name"
		)
		if fixed and accum and expense:
			rows.append(
				{
					"company_name": name,
					"fixed_asset_account": fixed,
					"accumulated_depreciation_account": accum,
					"depreciation_expense_account": expense,
				}
			)
	return rows


def _backfill_equipment_accounts():
	"""Add accounts rows to an existing Equipment category for companies missing them."""
	cat = frappe.get_doc("Asset Category", "Equipment")
	known = {r.company_name for r in cat.accounts}
	for row in _equipment_account_rows():
		if row["company_name"] not in known:
			cat.append("accounts", row)
	if not cat.finance_books:
		# Pre-existing categories often lack books: no depreciation runs,
		# so RLO transfers would halt nothing. Seed straight-line defaults.
		cat.append(
			"finance_books",
			{
				"depreciation_method": "Straight Line",
				"frequency_of_depreciation": 12,
				"total_number_of_depreciations": 60,
			},
		)
	if cat.has_value_changed("accounts") or cat.has_value_changed("finance_books"):
		cat.save(ignore_permissions=True)


def create_revenue_share_fee_item():
	"""Create the Revenue Share Fee non-stock item if absent."""
	_ensure_brand_others()
	if not frappe.db.exists("Item", "REVENUE-SHARE-FEE"):
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "REVENUE-SHARE-FEE",
				"item_name": "Revenue Share Fee",
				"description": "Revenue Share Fee",
				"item_group": "Services",
				"is_stock_item": 0,
				"brand": "Others",
			}
		)
		item.insert(ignore_permissions=True)


def create_shortfall_penalty_item():
	"""Create the Shortfall Penalty non-stock item if absent."""
	_ensure_brand_others()
	if not frappe.db.exists("Item", "SHORTFALL-PENALTY"):
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "SHORTFALL-PENALTY",
				"item_name": "Shortfall Penalty",
				"description": "Shortfall Penalty",
				"item_group": "Services",
				"is_stock_item": 0,
				"brand": "Others",
			}
		)
		item.insert(ignore_permissions=True)


def create_nbs_capital_asset_item():
	"""Create the shared capital asset fixed-asset item if absent."""
	_ensure_brand_others()
	_ensure_equipment_category()
	if not frappe.db.exists("Item", "Capital Asset"):
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "Capital Asset",
				"item_name": "Capital Asset",
				"description": "Generic capital asset item for capitalized placement analyzers.",
				"item_group": "Products",
				"is_fixed_asset": 1,
				"asset_category": "Equipment",
				"is_stock_item": 0,
				"brand": "Others",
			}
		)
		item.insert(ignore_permissions=True)


def _ensure_company_store_locations():
	"""Idempotent: ensure one `{abbr} - Store` Location per company.

	Newly capitalized placement analyzers start here with Warehouse
	status; deployment moves them to the customer site from here.
	"""
	for company in frappe.get_all("Company", pluck="name"):
		abbr = frappe.db.get_value("Company", company, "abbr") or company
		name = f"{abbr} - Store"
		if frappe.db.exists("Location", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Location",
				"location_name": name,
			}
		).insert(ignore_permissions=True)
