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


def ensure_linked_documents_on_submit(doc, method=None):
    ensure_customer_delivery_note(doc)
    ensure_promissory_note(doc)


@frappe.whitelist()
def create_customer_delivery_note_from_sales_order(sales_order: str) -> str:
    so_doc = frappe.get_doc("Sales Order", sales_order)
    _validate_sales_order_for_linked_docs(so_doc)
    name = _create_or_get_linked_doc_draft(so_doc, "Customer Delivery Note")
    return name


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
    link_field = (
        "custom_customer_delivery_note"
        if target_doctype == "Customer Delivery Note"
        else "custom_promissory_note"
    )
    flag_field = (
        "custom_has_customer_delivery_note"
        if target_doctype == "Customer Delivery Note"
        else "custom_has_promissory_note"
    )

    linked = getattr(so_doc, link_field, None)
    if linked:
        return linked

    existing = frappe.db.get_value(
        target_doctype,
        {"sales_order": so_doc.name, "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        frappe.db.set_value(
            "Sales Order",
            so_doc.name,
            {link_field: existing, flag_field: 1},
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

    # Link immediately so the Sales Order UI doesn't keep offering the Create button.
    frappe.db.set_value(
        "Sales Order",
        so_doc.name,
        {link_field: doc.name, flag_field: 1},
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


def ensure_customer_delivery_note(so_doc):
    if not so_doc or not getattr(so_doc, "name", None):
        return

    if getattr(so_doc, "custom_customer_delivery_note", None):
        return

    existing = frappe.db.get_value(
        "Customer Delivery Note",
        {"sales_order": so_doc.name, "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        frappe.db.set_value(
            "Sales Order",
            so_doc.name,
            {
                "custom_has_customer_delivery_note": 1,
            },
        )
        return

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
            "Customer billing/shipping address is required to create Customer Delivery Note. "
            "Please set addresses on the Sales Order or Customer."
        )

    cdn = frappe.get_doc(
        {
            "doctype": "Customer Delivery Note",
            "sales_order": so_doc.name,
            "date": nowdate(),
            "customer": so_doc.customer,
            "customer_address": customer_address,
            "shipping_address_name": shipping_address_name,
        }
    )
    cdn.insert(ignore_permissions=True)
    cdn.submit()


def ensure_promissory_note(so_doc):
    if not so_doc or not getattr(so_doc, "name", None):
        return

    if getattr(so_doc, "custom_promissory_note", None):
        return

    existing = frappe.db.get_value(
        "Promissory Note",
        {"sales_order": so_doc.name, "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        frappe.db.set_value(
            "Sales Order",
            so_doc.name,
            {
                "custom_has_promissory_note": 1,
            },
        )
        return

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
            "Customer billing/shipping address is required to create Promissory Note. "
            "Please set addresses on the Sales Order or Customer."
        )

    pn = frappe.get_doc(
        {
            "doctype": "Promissory Note",
            "sales_order": so_doc.name,
            "date": nowdate(),
            "customer": so_doc.customer,
            "customer_address": customer_address,
            "shipping_address_name": shipping_address_name,
        }
    )
    pn.insert(ignore_permissions=True)
    pn.submit()


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