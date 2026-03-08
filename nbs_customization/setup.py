import frappe

# The four items to inject, in display order after 'Sales Invoice'
NBS_SELLING_SIDEBAR_ITEMS = [
    {
        "label": "Customer Delivery Note",
        "type": "Link",
        "icon": "receipt",
        "link_to": "Customer Delivery Note",
        "link_type": "DocType",
        "icon": "es-line-truck",
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
        "icon": "es-line-handshake",
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
        "icon": "es-line-paper-plane",
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
        "icon": "es-line-transfer",
        "child": 1,
        "indent": 0,
        "collapsible": 1,
        "keep_closed": 0,
    },
]

NBS_LABELS = [item["label"] for item in NBS_SELLING_SIDEBAR_ITEMS]


def _get_expected_sequence(items):
    """
    Return the labels of our four items in the order they appear in the
    sidebar, or None if any are missing.
    """
    positions = {}
    for i, row in enumerate(items):
        if row.label in NBS_LABELS:
            positions[row.label] = i

    if len(positions) != len(NBS_LABELS):
        return None  # some items are missing

    return [label for label in NBS_LABELS if label in positions]


def _is_correctly_placed(items):
    """
    Returns True if all four NBS items are already present, in the correct
    order, and immediately follow 'Sales Invoice' with no gaps or duplicates.
    """
    # Check for duplicates
    nbs_rows = [row for row in items if row.label in set(NBS_LABELS)]
    if len(nbs_rows) != len(NBS_LABELS):
        return False

    # Find Sales Invoice position
    sales_invoice_idx = next(
        (i for i, row in enumerate(items) if row.label == "Sales Invoice"), None
    )
    if sales_invoice_idx is None:
        return False

    # Check our four items occupy exactly the four slots after Sales Invoice
    expected_slice = NBS_LABELS  # correct order
    actual_slice = [items[sales_invoice_idx + 1 + j].label for j in range(len(NBS_LABELS))
                    if sales_invoice_idx + 1 + j < len(items)]

    return actual_slice == expected_slice


def after_migrate():
    """
    Ensure NBS custom items are present in the Selling workspace sidebar,
    positioned immediately after 'Sales Invoice' and before 'POS'.

    Checks the current state first — if everything is already correct,
    does nothing. Only writes to the database when a change is needed.
    Idempotent and upgrade-safe.
    """
    if not frappe.db.exists("Workspace Sidebar", "Selling"):
        return

    sidebar = frappe.get_doc("Workspace Sidebar", "Selling")

    if _is_correctly_placed(sidebar.items):
        return  # nothing to do

    # Remove all NBS-managed rows (handles stale/duplicate/misplaced entries)
    nbs_label_set = set(NBS_LABELS)
    sidebar.items = [row for row in sidebar.items if row.label not in nbs_label_set]

    # Find insertion point — immediately after 'Sales Invoice'
    insert_idx = next(
        (i + 1 for i, row in enumerate(sidebar.items) if row.label == "Sales Invoice"),
        len(sidebar.items),  # fallback: append at end
    )

    # Splice in our four items
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

    # Re-index rows sequentially
    for i, row in enumerate(sidebar.items):
        row.idx = i + 1

    sidebar.flags.ignore_permissions = True
    sidebar.save()
    frappe.db.commit()