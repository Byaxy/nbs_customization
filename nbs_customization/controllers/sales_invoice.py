import frappe


def set_name_from_sales_order(doc, method):
    """
    Sets the Sales Invoice name based on its linked Sales Order.

    - First invoice against SO-0001  → SO-0001
    - Second invoice against SO-0001 → SO-0001-2
    - Third invoice against SO-0001  → SO-0001-3

    If no Sales Order reference is found, sets nothing and lets Frappe
    fall back to the standard naming series.
    """
    so_name = _get_sales_order(doc)
    if not so_name:
        return

    # Find all existing invoices whose name matches SO-XXXX or SO-XXXX-N
    existing = frappe.db.sql(
        """
        SELECT name FROM `tabSales Invoice`
        WHERE name = %(base)s
           OR name LIKE %(pattern)s
        """,
        {"base": so_name, "pattern": f"{so_name}-%"},
        as_dict=True,
    )

    if not existing:
        doc.name = so_name
    else:
        highest = 1
        for row in existing:
            parts = row.name[len(so_name):]  # "" or "-2" or "-3"
            if parts == "":
                continue
            try:
                suffix = int(parts.lstrip("-"))
                if suffix > highest:
                    highest = suffix
            except ValueError:
                pass

        doc.name = f"{so_name}-{highest + 1}"


def _get_sales_order(doc):
    """Return the Sales Order name from the first item row that has one."""
    for item in doc.items:
        if item.sales_order:
            return item.sales_order
    return None