"""
Overrides for the standard Sales Invoice DocType.
Currently handles:
  - Denormalizing the linked Sales Order(s) up to the SI header
    so that custom_sales_order is available in the list view,
    standard filters, and reports without any JOIN queries.
"""

import frappe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_sales_orders(doc):
    """
    Return a de-duplicated, ordered list of Sales Order names
    referenced across all SI items.  Order is preserved (first seen first).
    """
    seen = set()
    orders = []
    for item in doc.items:
        so = item.get("sales_order")
        if so and so not in seen:
            seen.add(so)
            orders.append(so)
    return orders


def _set_custom_sales_order(doc):
    """
    Populate custom_sales_order on the SI header.

    Rules
    -----
    - Single SO  →  store that SO name (normal Link behaviour).
    - Multiple SOs → store the first SO found.
      The field label will get a visual note appended via the list JS
      so users know there are additional SOs on the form.
    - No SO at all (e.g. direct sales invoice) → clear the field.
    """
    orders = _collect_sales_orders(doc)

    if orders:
        doc.custom_sales_order = orders[0]
    else:
        doc.custom_sales_order = None


# ---------------------------------------------------------------------------
# Hook entry-points  (referenced in hooks.py → doc_events)
# ---------------------------------------------------------------------------

def before_save(doc, method=None):
    _set_custom_sales_order(doc)


def before_submit(doc, method=None):
    """
    Re-run on submit so that any last-minute item changes are captured.
    (before_save runs first, but being explicit here is safer for
    workflows that skip the save step before submission.)
    """
    _set_custom_sales_order(doc)


def on_cancel(doc, method=None):
    """
    Clear the denormalized field on cancellation so cancelled SI
    do not pollute SO-based list filters.
    """
    doc.db_set("custom_sales_order", None, update_modified=False)