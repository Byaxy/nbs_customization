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
    }
   
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

    sales_invoice_idx = next(
        (i for i, row in enumerate(items) if row.label == "Sales Invoice"), None
    )
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

    anchor_idx = next(
        (i for i, row in enumerate(items) if row.label == EXPENSE_ANCHOR), None
    )
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


# ─── after_migrate entry point ────────────────────────────────────────────────

def after_migrate():
    """
    1. Inject NBS selling items into the Selling sidebar.
    2. Inject NBS expense group into both Accounting and Invoicing sidebars.
    Idempotent — only writes when a change is actually needed.
    """

    # ── Selling sidebar ──────────────────────────────────────────────────────
    if frappe.db.exists("Workspace Sidebar", "Selling"):
        sidebar = frappe.get_doc("Workspace Sidebar", "Selling")

        if not _is_correctly_placed(sidebar.items):
            nbs_label_set = set(NBS_LABELS)
            sidebar.items = [
                row for row in sidebar.items if row.label not in nbs_label_set
            ]

            insert_idx = next(
                (
                    i + 1
                    for i, row in enumerate(sidebar.items)
                    if row.label == "Sales Invoice"
                ),
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