"""
Overrides for the standard Purchase Invoice DocType.
Currently handles:
  - Denormalizing the linked Purchase Order(s) up to the PI header
    so that custom_purchase_order is available in the list view,
    standard filters, and reports without any JOIN queries.
"""

import frappe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_purchase_orders(doc):
    """
    Return a de-duplicated, ordered list of Purchase Order names
    referenced across all PI items.  Order is preserved (first seen first).
    """
    seen = set()
    orders = []
    for item in doc.items:
        po = item.get("purchase_order")
        if po and po not in seen:
            seen.add(po)
            orders.append(po)
    return orders


def _set_custom_purchase_order(doc):
    """
    Populate custom_purchase_order on the PI header.

    Rules
    -----
    - Single PO  →  store that PO name (normal Link behaviour).
    - Multiple POs → store the first PO found.
      The field label will get a visual note appended via the list JS
      so users know there are additional POs on the form.
    - No PO at all (e.g. direct receipt) → clear the field.
    """
    orders = _collect_purchase_orders(doc)

    if orders:
        doc.custom_purchase_order = orders[0]
    else:
        doc.custom_purchase_order = None


# ---------------------------------------------------------------------------
# Hook entry-points  (referenced in hooks.py → doc_events)
# ---------------------------------------------------------------------------

def before_save(doc, method=None):
    _set_custom_purchase_order(doc)


def before_submit(doc, method=None):
    """
    Re-run on submit so that any last-minute item changes are captured.
    (before_save runs first, but being explicit here is safer for
    workflows that skip the save step before submission.)
    """
    _set_custom_purchase_order(doc)


def on_cancel(doc, method=None):
    """
    Clear the denormalized field on cancellation so cancelled PRs
    do not pollute PO-based list filters.
    """
    doc.db_set("custom_purchase_order", None, update_modified=False)