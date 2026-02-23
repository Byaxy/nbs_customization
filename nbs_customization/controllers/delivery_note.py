import frappe
from frappe.utils import flt


# =========================================================
# VALIDATION
# =========================================================

def validate(doc, method=None):
    """
    Runs on EVERY Delivery Note validation.
    Only enforce rules if this is a Loan Conversion Waybill.
    """

    if doc.custom_waybill_type != "Loan Conversion Waybill":
        return

    validate_loan_source_warehouse(doc)
    validate_loan_stock_availability(doc)

def validate_loan_source_warehouse(doc):
    """
    Ensure Delivery Note warehouse matches
    the Loan Waybill target warehouse.
    """

    if not doc.custom_source_loan_waybill:
        frappe.throw("Loan Conversion Waybill must reference a Loan Waybill.")

    loan = frappe.get_doc("Loan Waybill", doc.custom_source_loan_waybill)

    if loan.docstatus != 1:
        frappe.throw("Linked Loan Waybill must be submitted.")

    if loan.conversion_status == "Fully Converted":
        frappe.throw("Loan Waybill is already fully converted.")

    for item in doc.items:
        if item.warehouse != loan.target_warehouse:
            frappe.throw(
                f"Row {item.idx}: Warehouse must be the customer loan warehouse "
                f"({loan.target_warehouse})."
            )

def validate_loan_stock_availability(doc):
    """
    Ensure quantities being delivered
    do not exceed remaining loan batch balances.
    """

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

# =========================================================
# ON SUBMIT
# =========================================================

def on_submit(doc, method=None):
    """
    When Delivery Note is submitted:
    apply FINAL loan deductions + history.
    """

    # Update Promissory Note for ALL Delivery Notes (regular and loan conversion)
    _update_promissory_note_directly(doc)
    
    # Commit the promissory note changes before continuing
    frappe.db.commit()

    if doc.custom_waybill_type != "Loan Conversion Waybill":
        return

    loan = frappe.get_doc("Loan Waybill", doc.custom_source_loan_waybill)

    # -----------------------------------------------------
    # LOCK LOAN + BATCH BALANCES (race-condition safety)
    # -----------------------------------------------------
    frappe.db.sql(
        "SELECT name FROM `tabLoan Waybill` WHERE name=%s FOR UPDATE",
        loan.name,
    )

    batch_rows = frappe.db.sql(
        """
        SELECT *
        FROM `tabLoan Waybill Batch Balance`
        WHERE parent=%s
        FOR UPDATE
        """,
        loan.name,
        as_dict=True,
    )

    balance_map = {}
    for b in batch_rows:
        key = (b.item_code, b.batch_no, b.serial_no)
        balance_map.setdefault(key, []).append(b)

    # -----------------------------------------------------
    # APPLY STRICT CONVERSION PER DN ITEM (exact batch/serial)
    # -----------------------------------------------------
    converted_by_item = {}

    for d in doc.items:
        qty_to_convert = flt(d.qty)
        if qty_to_convert <= 0:
            continue

        loan_item = next((i for i in loan.items if i.item_code == d.item_code), None)
        if not loan_item:
            frappe.throw(f"Item {d.item_code} not found in Loan Waybill {loan.name}.")

        if qty_to_convert > flt(loan_item.quantity_remaining):
            frappe.throw(f"Over-conversion detected for Item {d.item_code}.")

        key = (d.item_code, d.batch_no, d.serial_no)
        candidates = balance_map.get(key) or []
        if not candidates:
            frappe.throw(
                f"Row {d.idx}: No remaining loan balance row found for "
                f"Item {d.item_code}, Batch {d.batch_no or '-'}, Serial {d.serial_no or '-'}"
            )

        # If there are duplicates, pick the first row that can satisfy the qty.
        chosen = next((b for b in candidates if flt(b.qty_remaining) >= qty_to_convert), None)
        if not chosen:
            available = sum(flt(b.qty_remaining) for b in candidates)
            frappe.throw(
                f"Row {d.idx}: Cannot convert {qty_to_convert} of Item {d.item_code}, "
                f"Batch {d.batch_no or '-'}, Serial {d.serial_no or '-'}. "
                f"Only {available} remaining across matching balances."
            )

        new_remaining = flt(chosen.qty_remaining) - qty_to_convert
        new_converted = flt(chosen.qty_converted) + qty_to_convert

        frappe.db.set_value(
            "Loan Waybill Batch Balance",
            chosen.name,
            {"qty_remaining": new_remaining, "qty_converted": new_converted},
            update_modified=False,
        )

        frappe.db.sql(
            """
                INSERT INTO `tabLoan Conversion History`
                    (name, parent, parenttype, parentfield,
                     owner, creation, modified, modified_by,
                     conversion_date, delivery_note, sales_order,
                     item_code, quantity_converted,
                     batch_no, serial_no, loan_batch_balance)
                VALUES
                    (%(name)s, %(parent)s, %(parenttype)s, %(parentfield)s,
                     %(owner)s, NOW(), NOW(), %(modified_by)s,
                     %(conversion_date)s, %(delivery_note)s, %(sales_order)s,
                     %(item_code)s, %(quantity_converted)s,
                     %(batch_no)s, %(serial_no)s, %(loan_batch_balance)s)
            """,
            {
                "name": frappe.generate_hash(length=10),
                "parent": loan.name,
                "parenttype": "Loan Waybill",
                "parentfield": "conversion_history",
                "owner": frappe.session.user,
                "modified_by": frappe.session.user,
                "conversion_date": doc.posting_date,
                "delivery_note": doc.name,
                "sales_order": d.against_sales_order or None,
                "item_code": d.item_code,
                "quantity_converted": qty_to_convert,
                "batch_no": d.batch_no or None,
                "serial_no": d.serial_no or None,
                "loan_batch_balance": chosen.name,
            },
        )

        converted_by_item[d.item_code] = converted_by_item.get(d.item_code, 0) + qty_to_convert

    # -----------------------------------------------------
    # Update loan item totals (aggregate per item)
    # -----------------------------------------------------
    for item_code, qty in converted_by_item.items():
        loan_item = next((i for i in loan.items if i.item_code == item_code), None)
        if not loan_item:
            continue
        loan_item.quantity_converted = flt(loan_item.quantity_converted) + flt(qty)
        loan_item.quantity_remaining = flt(loan_item.quantity_loaned) - flt(loan_item.quantity_converted)

        frappe.db.set_value(
            "Loan Waybill Item",
            loan_item.name,
            {
                "quantity_converted": loan_item.quantity_converted,
                "quantity_remaining": loan_item.quantity_remaining,
            },
            update_modified=False,
        )

    # -----------------------------------------------------
    # Recalculate totals + status and persist
    # -----------------------------------------------------
    loan.calculate_totals()
    loan.update_overall_status()

    frappe.db.set_value(
        "Loan Waybill",
        loan.name,
        {
            "total_converted_quantity": loan.total_converted_quantity,
            "total_remaining_quantity": loan.total_remaining_quantity,
            "conversion_status":        loan.conversion_status,
        },
        update_modified=False,
    )


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
            pn_name = frappe.db.get_value(
                "Promissory Note",
                {"sales_order": sales_order, "docstatus": ["<", 2]},
                "name",
            )
            if pn_name:
                # Use the existing recalculate function which handles the save properly
                from nbs_customization.nbs_customization.doctype.promissory_note.promissory_note import recalculate_promissory_note_for_sales_order
                recalculate_promissory_note_for_sales_order(sales_order)
    except Exception as e:
        frappe.log_error(f"Failed to update Promissory Note: {str(e)}")




# =========================================================
# ON CANCEL
# =========================================================

def on_cancel(doc, method=None):
    """
    Reverse loan conversion when DN is cancelled.
    """
    # Check cancellation permissions
    if not frappe.has_permission("Delivery Note", "cancel", doc.name):
        frappe.throw("You do not have permission to cancel Delivery Notes.")
    
    try:
        # Update Promissory Note for ALL Delivery Notes (regular and loan conversion)
        _update_promissory_note_directly(doc)
        
        if doc.custom_waybill_type != "Loan Conversion Waybill":
            frappe.msgprint(f"Delivery Note {doc.name} cancelled successfully.")
            return

        loan = frappe.get_doc("Loan Waybill", doc.custom_source_loan_waybill)

        # -----------------------------------------------------
        # LOCK LOAN + BATCH BALANCES (race-condition safety)
        # -----------------------------------------------------
        frappe.db.sql(
            "SELECT name FROM `tabLoan Waybill` WHERE name=%s FOR UPDATE",
            loan.name,
        )

        frappe.db.sql(
            """
            SELECT name
            FROM `tabLoan Waybill Batch Balance`
            WHERE parent=%s
            FOR UPDATE
            """,
            loan.name,
        )

        # -----------------------------------------------------
        # RESTORE PRECISE BALANCES FROM CONVERSION HISTORY
        # -----------------------------------------------------
        history_rows = frappe.get_all(
            "Loan Conversion History",
            filters={"parent": loan.name, "delivery_note": doc.name},
            fields=["name", "item_code", "quantity_converted", "loan_batch_balance"],
        )

        restored_by_item = {}

        for h in history_rows:
            qty = flt(h.quantity_converted)
            if qty <= 0 or not h.loan_batch_balance:
                continue

            bb = frappe.db.get_value(
                "Loan Waybill Batch Balance",
                h.loan_batch_balance,
                ["qty_remaining", "qty_converted"],
                as_dict=True,
            )
            if not bb:
                continue

            frappe.db.set_value(
                "Loan Waybill Batch Balance",
                h.loan_batch_balance,
                {
                    "qty_converted": flt(bb.qty_converted) - qty,
                    "qty_remaining": flt(bb.qty_remaining) + qty,
                },
                update_modified=False,
            )

            restored_by_item[h.item_code] = restored_by_item.get(h.item_code, 0) + qty

        for item_code, qty in restored_by_item.items():
            loan_item = next((i for i in loan.items if i.item_code == item_code), None)
            if not loan_item:
                continue
            loan_item.quantity_converted = flt(loan_item.quantity_converted) - flt(qty)
            loan_item.quantity_remaining = flt(loan_item.quantity_loaned) - flt(loan_item.quantity_converted)

            frappe.db.set_value(
                "Loan Waybill Item",
                loan_item.name,
                {
                    "quantity_converted": loan_item.quantity_converted,
                    "quantity_remaining": loan_item.quantity_remaining,
                },
                update_modified=False,
            )

        # -----------------------------------------------------
        # Delete conversion history rows for this DN directly
        # -----------------------------------------------------
        frappe.db.sql("""
            DELETE FROM `tabLoan Conversion History`
            WHERE parent = %s AND delivery_note = %s
        """, (loan.name, doc.name))

        # -----------------------------------------------------
        # Recalculate totals + status and persist
        # -----------------------------------------------------
        loan.calculate_totals()
        loan.update_overall_status()

        frappe.db.set_value(
            "Loan Waybill",
            loan.name,
            {
                "total_converted_quantity": loan.total_converted_quantity,
                "total_remaining_quantity": loan.total_remaining_quantity,
                "conversion_status":        loan.conversion_status,
            },
            update_modified=False,
        )
        
        frappe.msgprint(f"Loan Conversion Delivery Note {doc.name} cancelled successfully.")
        
    except Exception as e:
        frappe.log_error(f"Delivery Note cancellation failed: {str(e)}")
        frappe.throw("Failed to cancel Delivery Note. Please check system logs.")