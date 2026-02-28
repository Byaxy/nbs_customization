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

@frappe.whitelist()
def create_promissory_note_from_sales_order(sales_order: str) -> str:
    so_doc = frappe.get_doc("Sales Order", sales_order)
    _validate_sales_order_for_linked_docs(so_doc)
    name = _create_or_get_linked_doc_draft(so_doc, "Promissory Note")
    return name


def _validate_sales_order_for_linked_docs(so_doc):
    if not so_doc or not getattr(so_doc, "name", None):
        frappe.throw("Sales Order is required")
    if so_doc.docstatus != 1:
        frappe.throw("Sales Order must be submitted")
    if not so_doc.customer:
        frappe.throw("Sales Order customer is required")


def _create_or_get_linked_doc_draft(so_doc, target_doctype: str) -> str:
    flag_field = (
        "custom_has_customer_delivery_note"
        if target_doctype == "Customer Delivery Note"
        else "custom_has_promissory_note"
    )

    existing = frappe.db.get_value(
        target_doctype,
        {"sales_order": so_doc.name, "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        frappe.db.set_value(
            "Sales Order",
            so_doc.name,
            {flag_field: 1},
        )
        return existing

    customer_address, shipping_address_name = _resolve_customer_addresses(so_doc)

    doc = frappe.get_doc(
        {
            "doctype": target_doctype,
            "sales_order": so_doc.name,
            "date": nowdate(),
            "customer": so_doc.customer,
            "customer_address": customer_address,
            "shipping_address_name": shipping_address_name,
        }
    )
    doc.insert(ignore_permissions=True)

    # Set the flag field so the Sales Order UI doesn't keep offering the Create button.
    frappe.db.set_value(
        "Sales Order",
        so_doc.name,
        {flag_field: 1},
    )

    return doc.name


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
                "stock_entry": bb.stock_entry,
                "stock_entry_detail": bb.stock_entry_detail,
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
def create_delivery_note_from_loan(
    loan_waybill: str,
    sales_order: str,
    items: Union[str, List[Dict]],
):
    """
    Create a DRAFT Delivery Note/Waybill (Loan Conversion Waybill)
    from selected Loan Waybill batch balances.
    """

    # ---------------------------------------------------------
    # PARSE + VALIDATE INPUT
    # ---------------------------------------------------------
    if isinstance(items, str):
        items = frappe.parse_json(items)

    if not isinstance(items, list):
        frappe.throw("Invalid items payload. Expected a list.")

    if not loan_waybill or not sales_order or not items:
        frappe.throw("Missing required conversion data.")

    # ---------------------------------------------------------
    # LOCK LOAN WAYBILL (prevents concurrent conversion)
    # ---------------------------------------------------------
    frappe.db.sql(
        """
        SELECT name FROM `tabLoan Waybill`
        WHERE name = %s
        FOR UPDATE
        """,
        loan_waybill,
    )

    loan = frappe.get_doc("Loan Waybill", loan_waybill)

    if loan.docstatus != 1:
        frappe.throw("Loan Waybill must be submitted.")

    if loan.conversion_status == "Fully Converted":
        frappe.throw("Loan Waybill already fully converted.")

    # ---------------------------------------------------------
    # LOCK BATCH BALANCES (FIFO ORDER)
    # ---------------------------------------------------------
    batch_rows = frappe.db.sql(
        """
        SELECT *
        FROM `tabLoan Waybill Batch Balance`
        WHERE parent = %s
          AND qty_remaining > 0
        ORDER BY creation ASC
        FOR UPDATE
        """,
        loan_waybill,
        as_dict=True,
    )

    if not batch_rows:
        frappe.throw("No remaining loan balances available.")

    # ---------------------------------------------------------
    # LOAD SALES ORDER + MAP ITEMS + GET REMAINING QTY
    # ---------------------------------------------------------
    so_doc = frappe.get_doc("Sales Order", sales_order)

    if so_doc.docstatus != 1:
        frappe.throw("Sales Order must be submitted before conversion.")

    so_item_map = {d.item_code: d for d in so_doc.items}
    so_remaining_map = get_so_remaining_quantities(sales_order)

    # ---------------------------------------------------------
    # BUILD BATCH BALANCE MAP (strict selection)
    # ---------------------------------------------------------
    balance_map: Dict[tuple, Dict] = {}
    for b in batch_rows:
        key = (b.item_code, b.batch_no, b.serial_no, b.stock_entry_detail)
        balance_map[key] = b

    # ---------------------------------------------------------
    # PREPARE DELIVERY NOTE (DRAFT ONLY)
    # ---------------------------------------------------------
    
    dn = frappe.get_doc(
        {
            "doctype": "Delivery Note",
            "posting_date": nowdate(),
            "customer": loan.customer,
            "set_warehouse": loan.target_warehouse,
            "sales_order": sales_order,
            "custom_waybill_type": "Loan Conversion Waybill",
            "custom_source_loan_waybill": loan_waybill,
            "custom_is_conversion": 1,
            "is_return": 0,
            "items": [],
        }
    )

    # ---------------------------------------------------------
    # RESOLVE ADDRESSES FROM SALES ORDER
    # ---------------------------------------------------------
    so_doc = frappe.get_doc("Sales Order", sales_order)
    customer_address, shipping_address_name = _resolve_customer_addresses(so_doc)
    
    dn.customer_address = customer_address
    dn.shipping_address_name = shipping_address_name

    # ---------------------------------------------------------
    # STRICT USER-SELECTION (VALIDATION ONLY — NO MUTATION)
    # ---------------------------------------------------------
    for row in items:
        item_code = row.get("item_code")
        qty = flt(row.get("qty"))
        batch_no = row.get("batch_no")
        serial_no = row.get("serial_no")
        stock_entry_detail = row.get("stock_entry_detail")

        if not item_code or qty <= 0:
            continue

        if item_code not in so_item_map:
            frappe.throw(
                f"Item {item_code} does not exist in Sales Order {sales_order}."
            )

        key = (item_code, batch_no, serial_no, stock_entry_detail)
        balance = balance_map.get(key)

        if not balance:
            frappe.throw(
                f"No remaining loan balance row found for Item {item_code}, "
                f"Batch {batch_no or '-'}, Serial {serial_no or '-'} (selection mismatch)."
            )

        remaining = flt(balance.get("qty_remaining"))
        if remaining <= 0:
            frappe.throw(
                f"No remaining loan balance for Item {item_code}, "
                f"Batch {batch_no or '-'}, Serial {serial_no or '-'}"
            )

        if qty > remaining:
            frappe.throw(
                f"Cannot convert {qty} of Item {item_code}, Batch {batch_no or '-'}, "
                f"Serial {serial_no or '-'}. Only {remaining} remaining in loan balance."
            )
        
        # Validate against Sales Order remaining quantity
        so_remaining = so_remaining_map.get(item_code, 0)
        if so_remaining <= 0:
            frappe.throw(
                f"Cannot convert Item {item_code}. No remaining quantity in Sales Order {sales_order}."
            )
        
        if qty > so_remaining:
            frappe.throw(
                f"Cannot convert {qty} of Item {item_code}, Batch {batch_no or '-'}, "
                f"Serial {serial_no or '-'}. Only {so_remaining} remaining in Sales Order {sales_order}."
            )

        so_item = so_item_map[item_code]

        dn.append(
            "items",
            {
                "item_code": item_code,
                "qty": qty,
                "uom": frappe.db.get_value("Item", item_code, "stock_uom"),
                "warehouse": loan.target_warehouse,
                "batch_no": batch_no,
                "serial_no": serial_no,
                "against_sales_order": sales_order,
                "so_detail": so_item.name,
                "rate": balance.get("valuation_rate"),
                "use_serial_batch_fields": 1,
            },
        )

    if not dn.items:
        frappe.throw("No valid quantities provided for conversion.")

    # ---------------------------------------------------------
    # INSERT DELIVERY NOTE (STILL DRAFT)
    # ---------------------------------------------------------
    dn.insert(ignore_permissions=True)

    # ---------------------------------------------------------
    # REFRESH LOAN STATUS (READ-ONLY UPDATE)
    # ---------------------------------------------------------
    loan.reload()
    loan.calculate_totals()
    loan.update_overall_status()
    loan.db_update()

    # ---------------------------------------------------------
    # ATOMIC COMMIT
    # ---------------------------------------------------------
    frappe.db.commit()

    return dn.name

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