import frappe
from frappe.utils import flt, nowdate
from typing import Union, List, Dict


def get_so_remaining_quantities(sales_order: str) -> Dict[str, float]:
    """
    Calculate remaining quantities for each item in a Sales Order
    by subtracting delivered quantities from all Delivery Notes.
    
    Returns: Dict mapping item_code → remaining_qty
    """
    if not sales_order:
        return {}
    
    # Get SO item quantities
    so_items = frappe.get_all(
        "Sales Order Item",
        filters={"parent": sales_order},
        fields=["item_code", "qty"]
    )
    
    so_qty_map = {item.item_code: flt(item.qty) for item in so_items}
    
    # Get delivered quantities from all submitted Delivery Notes against this SO
    delivered_qty = frappe.db.sql(
        """
        SELECT dn_item.item_code, SUM(dn_item.qty) as delivered_qty
        FROM `tabDelivery Note Item` dn_item
        INNER JOIN `tabDelivery Note` dn ON dn_item.parent = dn.name
        WHERE dn.docstatus = 1
          AND dn_item.against_sales_order = %s
        GROUP BY dn_item.item_code
        """,
        sales_order,
        as_dict=True
    )
    
    delivered_qty_map = {item.item_code: flt(item.delivered_qty) for item in delivered_qty}
    
    # Calculate remaining quantities
    remaining_map = {}
    for item_code, so_qty in so_qty_map.items():
        delivered = delivered_qty_map.get(item_code, 0)
        remaining = flt(so_qty - delivered)
        if remaining > 0:
            remaining_map[item_code] = remaining
    
    return remaining_map


@frappe.whitelist()
def make_customer_delivery_note(source_name: str, target_doc=None, ignore_permissions=None):
    from frappe.model.mapper import get_mapped_doc

    def set_missing_values(source, target):
        customer_address, shipping_address_name = _resolve_customer_addresses(source)
        target.customer_address = customer_address
        target.shipping_address_name = shipping_address_name
        target.date = nowdate()
        target.run_method("set_missing_values")

    return get_mapped_doc(
        "Sales Order",
        source_name,
        {
            "Sales Order": {
                "doctype": "Customer Delivery Note",
                "field_map": {
                    "name": "sales_order",
                    "customer": "customer",
                    "customer_name": "customer_name",
                    "customer_address": "customer_address",
                    "shipping_address_name": "shipping_address_name",
                },
                "validation": {
                    "docstatus": ["=", 1],
                },
            },
            "Sales Order Item": {
                "doctype": "Customer Delivery Note Item",
                "field_map": {
                    "item_code": "item_code",
                    "description": "description",
                    "qty": "qty_requested",
                },
                "postprocess": lambda source, target, source_parent: target.update({
                    "qty_supplied": source.qty,
                    "balance_left": 0,
                }),
                "add_if_empty": True,
            },
        },
        target_doc,
        set_missing_values,
    )

@frappe.whitelist()
def make_promissory_note(source_name, target_doc=None, ignore_permissions=None):
    """
    Maps SO → new unsaved Promissory Note via get_mapped_doc.
    Called by frappe.model.open_mapped_doc from the SO form button.
    Items are set server-side based on SO qty minus delivered qty.
    """
    from frappe.model.mapper import get_mapped_doc
    from frappe.utils import nowdate, flt

    def set_missing_values(source, target):
        target.date = nowdate()

        # Resolve addresses
        target.customer_address = getattr(source, "customer_address", None) or \
            frappe.db.get_value("Customer", source.customer, "customer_primary_address")
        target.shipping_address_name = getattr(source, "shipping_address_name", None) \
            or target.customer_address

        if not target.customer_address or not target.shipping_address_name:
            frappe.throw(
                "Could not resolve billing/shipping address from Sales Order. "
                "Please set addresses on the Customer."
            )

        # Compute delivered quantities for each SO item
        delivered_rows = frappe.db.sql(
            """
            SELECT dni.item_code, SUM(dni.qty) AS qty
            FROM `tabDelivery Note Item` dni
            INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
            WHERE dn.docstatus = 1
              AND dn.is_return = 0
              AND IFNULL(dni.against_sales_order, '') = %s
            GROUP BY dni.item_code
            """,
            (source_name,),
            as_dict=True,
        )
        delivered_by_item = {r.item_code: flt(r.qty) for r in delivered_rows}

        # Patch qty_remaining and sub_total on mapped child rows
        total = 0.0
        any_remaining = False
        nothing_delivered = True

        for item in target.items:
            delivered = delivered_by_item.get(item.item_code, 0.0)
            so_qty = flt(item.qty_remaining)
            item.qty_remaining = max(0.0, so_qty - delivered)
            item.sub_total = item.qty_remaining * flt(item.unit_price)
            total += item.sub_total

            if item.qty_remaining > 0:
                any_remaining = True
            if delivered > 0:
                nothing_delivered = False

        target.total_amount = total

        if not target.items:
            target.promissory_note_status = "Pending"
        elif not any_remaining:
            target.promissory_note_status = "Fulfilled"
        elif nothing_delivered:
            target.promissory_note_status = "Pending"
        else:
            target.promissory_note_status = "Partially Fulfilled"

    return get_mapped_doc(
        "Sales Order",
        source_name,
        {
            "Sales Order": {
                "doctype": "Promissory Note",
                "field_map": {
                    "name": "sales_order",
                    "customer": "customer",
                    "customer_name": "customer_name",
                },
                "validation": {"docstatus": ["=", 1]},
            },
            "Sales Order Item": {
                "doctype": "Promissory Note Item",
                "field_map": {
                    "item_code": "item_code",
                    "description": "description",
                    "qty": "qty_remaining",   # raw SO qty; patched in set_missing_values
                    "rate": "unit_price",
                    "uom": "uom",
                },
                "add_if_empty": True,
            },
        },
        target_doc,
        set_missing_values,
        ignore_permissions=ignore_permissions,
    )


def _resolve_customer_addresses(so_doc) -> tuple[str, str]:
    customer_address = getattr(so_doc, "customer_address", None) or frappe.get_value(
        "Customer", so_doc.customer, "customer_primary_address"
    )
    shipping_address_name = getattr(so_doc, "shipping_address_name", None)

    if not customer_address:
        customer_address = _get_default_customer_address(so_doc.customer)

    if not shipping_address_name:
        shipping_address_name = _get_default_shipping_address(so_doc.customer) or customer_address

    if not customer_address or not shipping_address_name:
        frappe.throw(
            "Customer billing/shipping address is required. Please set addresses on the Sales Order or Customer."
        )

    return customer_address, shipping_address_name


def _get_default_customer_address(customer: str) -> str | None:
    try:
        from frappe.contacts.doctype.address.address import get_default_address
    except Exception:
        return None

    try:
        return get_default_address("Customer", customer)
    except Exception:
        return None


def _get_default_shipping_address(customer: str) -> str | None:
    try:
        from frappe.contacts.doctype.address.address import get_default_address
    except Exception:
        return None

    try:
        return get_default_address("Customer", customer, sort_key="is_shipping_address")
    except Exception:
        return None

@frappe.whitelist()
def get_pending_loan_waybills(sales_order: str):
    """
    Return pending loan waybills that contain
    remaining batch/serial quantities matching
    items in the given Sales Order.
    """

    if not sales_order:
        frappe.throw("Sales Order is required")

    so = frappe.get_doc("Sales Order", sales_order)

    customer = so.customer
    item_codes = {row.item_code for row in so.items}
    
    # Get SO remaining quantities
    so_remaining_map = get_so_remaining_quantities(sales_order)

    # Fetch candidate loan waybills in FIFO order
    loans = frappe.get_all(
        "Loan Waybill",
        filters={
            "customer": customer,
            "docstatus": 1,
            "conversion_status": ["!=", "Fully Converted"],
        },
        fields=["name", "loan_date"],
        order_by="loan_date asc",
    )

    results = []

    for loan in loans:
        loan_doc = frappe.get_doc("Loan Waybill", loan.name)

        matching_items = []

        # --------------------------------------------
        # CHECK AGAINST BATCH BALANCES (true stock)
        # --------------------------------------------
        for bb in loan_doc.batch_balances:

            if bb.item_code not in item_codes:
                continue

            remaining_qty = flt(bb.qty_remaining)
            if remaining_qty <= 0:
                continue
            
            # Get SO remaining for this item
            so_remaining = so_remaining_map.get(bb.item_code, 0)
            if so_remaining <= 0:
                continue  # No SO remaining, skip this item
            
            # Calculate max convertible quantity
            max_convertible_qty = min(remaining_qty, so_remaining)
            if max_convertible_qty <= 0:
                continue

            matching_items.append({
                "item_code": bb.item_code,
                "description": bb.description,
                "qty_loaned": flt(bb.qty_loaned),
                "qty_converted": flt(bb.qty_converted),
                "qty_remaining": remaining_qty,
                "so_qty_remaining": so_remaining,
                "max_convertible_qty": max_convertible_qty,
                "batch_no": bb.batch_no,
                "serial_no": bb.serial_no,
                "expiry_date": bb.expiry_date,
                "warehouse": bb.warehouse,
            })

        if matching_items:
            results.append({
                "loan_waybill": loan.name,
                "loan_date": loan.loan_date,
                "items": matching_items,
            })

    return {
        "customer": customer,
        "sales_order": sales_order,
        "loan_waybills": results,
    }

@frappe.whitelist()
def has_pending_loan_waybills(customer, sales_order):
    """
    Check if customer has any pending loan waybills with items matching sales order.
    Returns True immediately upon finding the first matching item with remaining quantity.
    Optimized for performance - stops at first match.
    """
    if not customer or not sales_order:
        return False
    
    # Get sales order items
    so_items_query = """
        SELECT DISTINCT item_code 
        FROM `tabSales Order Item` 
        WHERE parent = %s 
        AND docstatus = 1
    """
    so_items = frappe.db.sql(so_items_query, (sales_order,), as_dict=True)
    
    if not so_items:
        return False
    
    # Check if any pending loan waybill has matching items with remaining quantity
    item_codes = [item.item_code for item in so_items]
    
    # Use EXISTS query for maximum performance
    exists_query = """
        SELECT 1 
        FROM `tabLoan Waybill Batch Balance` lwbb
        INNER JOIN `tabLoan Waybill` lw ON lwbb.parent = lw.name
        WHERE lw.customer = %s 
        AND lw.docstatus = 1 
        AND lw.conversion_status != 'Fully Converted'
        AND lwbb.item_code IN %s
        AND lwbb.qty_remaining > 0
        LIMIT 1
    """
    
    result = frappe.db.sql(exists_query, (customer, item_codes), as_dict=True)
    return len(result) > 0


@frappe.whitelist()
def make_delivery_note_from_loan(source_name: str, target_doc=None, ignore_permissions=None):
    """
    Maps Loan Waybill → new unsaved Delivery Note (Loan Conversion Waybill) via get_mapped_doc.
    Follows ERPNext best practices like make_customer_delivery_note and make_promissory_note.
    Items are mapped from selected batch balances with validation.
    """
    from frappe.model.mapper import get_mapped_doc
    from frappe.utils import nowdate, flt

    # Get the args from the frappe.form_dict (set by frappe.model.open_mapped_doc)
    args = frappe.form_dict.get('args', {})
    if isinstance(args, str):
        args = frappe.parse_json(args)
    
    sales_order = args.get('sales_order')
    items = args.get('items')
    
    if not sales_order or not items:
        frappe.throw("Sales Order and items are required for loan conversion.")

    def set_missing_values(source, target):
        # Set basic delivery note fields
        target.posting_date = nowdate()
        target.set_warehouse = source.target_warehouse
        target.custom_waybill_type = "Loan Conversion Waybill"
        target.custom_source_loan_waybill = source.name
        target.custom_is_conversion = 1
        target.is_return = 0
        target.sales_order = sales_order
        
        # Resolve addresses from Sales Order
        if sales_order:
            so_doc = frappe.get_doc("Sales Order", sales_order)
            customer_address, shipping_address_name = _resolve_customer_addresses(so_doc)
            target.customer_address = customer_address
            target.shipping_address_name = shipping_address_name

    def postprocess_source(doc, source, target):
        """Validate loan waybill status before mapping"""
        if doc.docstatus != 1:
            frappe.throw("Loan Waybill must be submitted.")
        
        if doc.conversion_status == "Fully Converted":
            frappe.throw("Loan Waybill already fully converted.")

    def condition(doc):
        """Only include batch balances that are in the selected items"""
        # Parse selected items
        if isinstance(items, str):
            selected_items = frappe.parse_json(items)
        else:
            selected_items = items
        
        # Check if this batch balance is in selected items
        for selected in selected_items:
            if (selected.get('item_code') == doc.item_code and 
                selected.get('batch_no') == doc.batch_no and 
                selected.get('serial_no') == doc.serial_no and
                flt(selected.get('qty', 0)) > 0):
                
                return True
        
        return False

    def postprocess_item(source, target, source_parent):
        """Set quantity from selected items - only called for items that passed condition"""
        # Parse selected items
        if isinstance(items, str):
            selected_items = frappe.parse_json(items)
        else:
            selected_items = items
        
        # Find the matching selected item and set its quantity
        for selected in selected_items:
            if (selected.get('item_code') == source.item_code and 
                selected.get('batch_no') == source.batch_no and 
                selected.get('serial_no') == source.serial_no and
                flt(selected.get('qty', 0)) > 0):
                
                # Update quantity from selection
                target.qty = flt(selected.get('qty', 0))
                target.rate = flt(selected.get('valuation_rate', source.valuation_rate))
                
                # Set mandatory fields from Item master
                item_details = frappe.db.get_value("Item", source.item_code, 
                    ["item_name", "description", "stock_uom"], as_dict=True)
                
                if item_details:
                    target.item_name = item_details.item_name
                    target.description = item_details.description
                    target.uom = item_details.stock_uom
                    target.use_serial_batch_fields = 1
                
                # Set Sales Order reference
                so_item = frappe.db.get_value("Sales Order Item", 
                    filters={"parent": sales_order, "item_code": source.item_code},
                    fieldname="name")
                if so_item:
                    target.against_sales_order = sales_order
                    target.so_detail = so_item
                return

    def validate_batch_balance(source, target, source_parent):
        """Validate that batch balance has remaining quantity"""
        if flt(source.qty_remaining) <= 0:
            frappe.throw(
                f"No remaining loan balance for Item {source.item_code}, "
                f"Batch {source.batch_no or '-'}, Serial {source.serial_no or '-'}"
            )

    return get_mapped_doc(
        "Loan Waybill",
        source_name,
        {
            "Loan Waybill": {
                "doctype": "Delivery Note",
                "field_map": {
                    "customer": "customer",
                    "customer_name": "customer_name",
                    "target_warehouse": "set_warehouse",
                    "name": "custom_source_loan_waybill",
                },
                "validation": {
                    "docstatus": ["=", 1],
                },
                "postprocess": postprocess_source,
            },
            "Loan Waybill Batch Balance": {
                "doctype": "Delivery Note Item",
                "field_map": {
                    "item_code": "item_code",
                    "batch_no": "batch_no", 
                    "serial_no": "serial_no",
                    "warehouse": "warehouse",
                    "valuation_rate": "rate",
                    "qty_remaining": "qty",  # Will be updated in postprocess_item
                },
                "condition": condition,  # ← KEY: Filter before mapping!
                "postprocess": postprocess_item,
                "add_if_empty": False,
            },
        },
        target_doc,
        set_missing_values,
        ignore_permissions=ignore_permissions,
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def sales_order_query(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql(
        """
        SELECT name, customer, transaction_date
        FROM `tabSales Order`
        WHERE docstatus = 1
          AND (%(txt)s = "" OR name LIKE %(txt)s OR customer LIKE %(txt)s)
          AND name NOT IN (
              SELECT sales_order FROM `tabCustomer Delivery Note`
              WHERE docstatus < 2
                AND sales_order IS NOT NULL
                AND name != %(current_doc)s
          )
        ORDER BY transaction_date DESC
        LIMIT %(page_len)s OFFSET %(start)s
        """,
        {
            "txt": f"%{txt}%",
            "current_doc": filters.get("current_doc") or "",
            "page_len": page_len,
            "start": start,
        },
    )

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def promissory_note_sales_order_query(doctype, txt, searchfield, start, page_len, filters):
    """
    Link field query for Promissory Note → Sales Order.
    Only shows submitted SOs that don't already have an active PN,
    except for the current document's own SO.
    """
    return frappe.db.sql(
        """
        SELECT name, customer, transaction_date
        FROM `tabSales Order`
        WHERE docstatus = 1
          AND (%(txt)s = "" OR name LIKE %(txt)s OR customer LIKE %(txt)s)
          AND name NOT IN (
              SELECT sales_order FROM `tabPromissory Note`
              WHERE docstatus < 2
                AND sales_order IS NOT NULL
                AND name != %(current_doc)s
          )
        ORDER BY transaction_date DESC
        LIMIT %(page_len)s OFFSET %(start)s
        """,
        {
            "txt": f"%{txt}%",
            "current_doc": filters.get("current_doc") or "",
            "page_len": page_len,
            "start": start,
        },
    )

