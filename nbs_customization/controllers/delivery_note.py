import frappe
from frappe.utils import flt


# VALIDATION

def validate(doc, method=None):

    if doc.custom_waybill_type != "Loan Conversion Waybill":
        return

    validate_loan_source_warehouse(doc)
    validate_loan_stock_availability(doc)

def validate_loan_source_warehouse(doc):

    if not doc.custom_source_loan_waybill:
        frappe.throw("Loan Conversion Waybill must reference a Loan Waybill.")

    loan = frappe.get_doc("Loan Waybill", doc.custom_source_loan_waybill)

    if loan.docstatus != 1:
        frappe.throw("Linked Loan Waybill must be submitted.")

    if loan.conversion_status == "Fully Converted":
        frappe.throw("Loan Waybill is already fully converted.")

    # Validate that target warehouse belongs to customer (consistent with Loan Waybill validation)
    if loan.customer:
        customer_name = frappe.db.get_value("Customer", loan.customer, "customer_name")
        if not customer_name:
            customer_name = loan.customer
        
        # Check if customer name is contained in warehouse name
        if customer_name.lower() not in loan.target_warehouse.lower():
            frappe.throw(
                f"Target warehouse '{loan.target_warehouse}' must contain '{customer_name}' in name. "
                f"Please select customer loan warehouse or create one"
            )

    for item in doc.items:
        if item.warehouse != loan.target_warehouse:
            frappe.throw(
                f"Row {item.idx}: Warehouse must be the customer loan warehouse "
                f"({loan.target_warehouse})."
            )

def validate_loan_stock_availability(doc):

    loan = frappe.get_doc("Loan Waybill", doc.custom_source_loan_waybill)

    # Build remaining balance map
    balances = frappe.get_all(
        "Loan Waybill Batch Balance",
        filters={"parent": loan.name},
        fields=[
            "name",
            "item_code",
            "batch_no",
            "serial_no",
            "qty_remaining",
        ],
    )

    balance_map = {}
    for b in balances:
        key = (b.item_code, b.batch_no, b.serial_no)
        balance_map.setdefault(key, []).append(b)

    # Validate each DN row
    for item in doc.items:
        key = (item.item_code, item.batch_no, item.serial_no)

        candidates = balance_map.get(key) or []

        if not candidates:
            frappe.throw(
                f"Row {item.idx}: No remaining loan balance for "
                f"Item {item.item_code}, Batch {item.batch_no or '-'}, "
                f"Serial {item.serial_no or '-'}"
            )

        chosen = next((b for b in candidates if flt(b.qty_remaining) >= flt(item.qty)), None)
        if not chosen:
            available = sum(flt(b.qty_remaining) for b in candidates)
            frappe.throw(
                f"Row {item.idx}: Cannot deliver {item.qty} of "
                f"{item.item_code}. Only {available} remaining across matching loan balances."
            )

def before_save(doc, method=None):
    _set_custom_sales_order(doc)


def before_submit(doc, method=None):
    """
    Re-run on submit so that any last-minute item changes are captured.
    (before_save runs first, but being explicit here is safer for
    workflows that skip the save step before submission.)
    """
    _set_custom_sales_order(doc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_sales_orders(doc):
    """
    Return a de-duplicated, ordered list of Sales Order names
    referenced across all DN items.  Order is preserved (first seen first).
    """
    seen = set()
    orders = []
    for item in doc.items:
        so = item.get("against_sales_order")
        if so and so not in seen:
            seen.add(so)
            orders.append(so)
    return orders


def _set_custom_sales_order(doc):
    """
    Populate custom_sales_order on the DN header.

    Rules
    -----
    - Single SO  →  store that SO name (normal Link behaviour).
    - Multiple SOs → store the first SO found.
      The field label will get a visual note appended via the list JS
      so users know there are additional SOs on the form.
    - No SO at all (e.g. direct delivery note) → clear the field.
    """
    orders = _collect_sales_orders(doc)

    if orders:
        doc.custom_sales_order = orders[0]
    else:
        doc.custom_sales_order = None


# AFTER SUBMIT

def on_submit(doc, method=None):

    _update_promissory_note_directly(doc)


    if doc.custom_waybill_type != "Loan Conversion Waybill":
        return

    _apply_loan_conversion(doc)


# CANCEL

def on_cancel(doc, method=None):
    """
    Reverse loan conversion when DN is cancelled.
    """
    # Check cancellation permissions
    if not frappe.has_permission("Delivery Note", "cancel", doc.name):
        frappe.throw("You do not have permission to cancel Delivery Notes.")
    
    try:
        _update_promissory_note_directly(doc)
        
        if doc.custom_waybill_type != "Loan Conversion Waybill":
            frappe.msgprint(f"Delivery Note {doc.name} cancelled successfully.")
            return

        _reverse_loan_conversion(doc)
        
        frappe.msgprint(f"Loan Conversion Delivery Note {doc.name} cancelled successfully.")

    except Exception as e:
        frappe.log_error(f"Delivery Note cancellation failed: {str(e)}")
        frappe.throw("Failed to cancel Delivery Note. Please check system logs.")


def _update_promissory_note_directly(doc):
    """Update Promissory Note after Delivery Note is committed"""
    try:
        items = getattr(doc, "items", None) or []
        
        sales_orders = {
            getattr(d, "against_sales_order", None)
            for d in items
            if getattr(d, "against_sales_order", None)
        }

        for sales_order in sales_orders:

            from nbs_customization.nbs_customization.doctype.promissory_note.promissory_note import recalculate_promissory_note_for_sales_order
            recalculate_promissory_note_for_sales_order(sales_order)
    except Exception as e:
        frappe.log_error(f"Failed to update Promissory Note: {str(e)}")


def _apply_loan_conversion(dn):
    """Called on Delivery Note submit. Updates the source Loan Waybill."""
    loan_waybill_name = dn.custom_source_loan_waybill
    if not loan_waybill_name:
        frappe.throw(
            _(
                "Delivery Note {0} is marked as a Loan Conversion Waybill "
                "but has no Source Loan Waybill set."
            ).format(dn.name)
        )

    loan_doc = frappe.get_doc("Loan Waybill", loan_waybill_name)

    if loan_doc.docstatus != 1:
        frappe.throw(
            _("Source Loan Waybill {0} is not submitted.").format(loan_waybill_name)
        )

    if loan_doc.conversion_status == "Fully Converted":
        frappe.throw(
            _("Source Loan Waybill {0} is already fully converted.").format(loan_waybill_name)
        )

    items = _extract_conversion_items(dn)
    loan_doc.apply_conversion(dn.name, items)


def _reverse_loan_conversion(dn):
    """Called on Delivery Note cancel. Reverses changes on the source Loan Waybill."""
    loan_waybill_name = dn.custom_source_loan_waybill
    if not loan_waybill_name:
        return  # Nothing to reverse if no source is set

    if not frappe.db.exists("Loan Waybill", loan_waybill_name):
        return  # Source was deleted — nothing to reverse

    loan_doc = frappe.get_doc("Loan Waybill", loan_waybill_name)

    if loan_doc.docstatus == 2:
        return  # Source already cancelled — nothing to reverse

    items = _extract_conversion_items(dn)
    loan_doc.reverse_conversion(dn.name, items)


def _extract_conversion_items(dn):
    """
    Build the items payload for apply_conversion / reverse_conversion
    from the Delivery Note item rows.

    Returns list of:
        { item_code, batch_no, serial_no, qty_converted }
    """
    return [
        {
            "item_code": item.item_code,
            "batch_no": item.batch_no or None,
            "serial_no": item.serial_no or None,
            "qty_converted": flt(item.qty),
        }
        for item in dn.items
        if item.item_code and flt(item.qty)
    ]