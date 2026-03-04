# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class LoanWaybill(Document):

    # =========================================================
    # VALIDATION
    # =========================================================

    def validate(self):
        self._block_amend()
        self._validate_warehouses()
        self._validate_stock_availability()
        self._calculate_totals()
        self._update_conversion_status()

    def _block_amend(self):
        if self.amended_from:
            frappe.throw(
                _(
                    "Amending a Loan Waybill is not permitted. "
                    "Cancel the original and create a new Loan Waybill instead."
                )
            )

    def _validate_warehouses(self):
        if not self.source_warehouse or not self.target_warehouse:
            frappe.throw(_("Source Warehouse and Target Warehouse are both mandatory."))

        if self.source_warehouse == self.target_warehouse:
            frappe.throw(_("Source Warehouse and Target Warehouse cannot be the same."))

        # Soft warning — adjust to your warehouse naming / custom field convention.
        if self.customer and self.customer.lower() not in self.target_warehouse.lower():
            frappe.throw(
                _(
                    "Target Warehouse '{0}' must be '{1}' loan warehouse. "
                    "Please select customer loan warehouse or create one"
                ).format(self.target_warehouse, self.customer)
            )

    def _validate_stock_availability(self):
        """Check the source warehouse has sufficient actual qty for each item."""
        for item in self.items:
            if not item.item_code or not flt(item.quantity_loaned):
                continue

            actual_qty = (
                frappe.db.get_value(
                    "Bin",
                    {"item_code": item.item_code, "warehouse": self.source_warehouse},
                    "actual_qty",
                )
                or 0
            )

            if flt(actual_qty) < flt(item.quantity_loaned):
                frappe.throw(
                    _(
                        "Insufficient stock for Item {0} in Warehouse {1}. "
                        "Available: {2}, Requested: {3}."
                    ).format(
                        item.item_code,
                        self.source_warehouse,
                        flt(actual_qty),
                        flt(item.quantity_loaned),
                    )
                )

    # =========================================================
    # TOTALS & STATUS
    # =========================================================

    def _calculate_totals(self):
        self.total_loan_quantity = 0.0
        self.total_converted_quantity = 0.0
        self.total_remaining_quantity = 0.0

        for item in self.items:
            item.quantity_remaining = flt(item.quantity_loaned) - flt(item.quantity_converted)
            self.total_loan_quantity += flt(item.quantity_loaned)
            self.total_converted_quantity += flt(item.quantity_converted)
            self.total_remaining_quantity += flt(item.quantity_remaining)

    def _update_conversion_status(self):
        """Derive conversion_status from totals. Always call after _calculate_totals."""
        if self.docstatus == 0:
            self.conversion_status = "Draft"
            return
        if self.docstatus == 2:
            self.conversion_status = "Cancelled"
            return
        # submitted
        if all(flt(i.quantity_remaining) == 0 for i in self.items):
            self.conversion_status = "Fully Converted"
        elif all(flt(i.quantity_converted) == 0 for i in self.items):
            self.conversion_status = "Pending"
        else:
            self.conversion_status = "Partially Converted"

    # =========================================================
    # SUBMIT
    # =========================================================

    def on_submit(self):
        stock_entry = self._create_loan_stock_entry()
        self._sync_batch_balances(stock_entry)
        self._calculate_totals()
        self.db_set("conversion_status", "Pending", update_modified=False)

    def _create_loan_stock_entry(self):
        """
        Create and submit a Material Transfer Stock Entry:
        source_warehouse → target_warehouse.
        Marks SE with custom_is_loan=1 so the cancel guard in
        stock_entry.py blocks direct cancellation outside this module.
        """
        if self.stock_entry:
            return frappe.get_doc("Stock Entry", self.stock_entry)

        se = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Transfer",
                "posting_date": self.loan_date,
                "from_warehouse": self.source_warehouse,
                "to_warehouse": self.target_warehouse,
                "custom_is_loan": 1,
                "items": [
                    {
                        "item_code": item.item_code,
                        "qty": flt(item.quantity_loaned),
                        "uom": item.uom,
                        "s_warehouse": self.source_warehouse,
                        "t_warehouse": self.target_warehouse,
                        "basic_rate": flt(item.rate),
                    }
                    for item in self.items
                    if item.item_code and flt(item.quantity_loaned)
                ],
            }
        )
        se.insert(ignore_permissions=True)
        se.submit()
        self.db_set("stock_entry", se.name, update_modified=False)
        return se

    # =========================================================
    # BATCH BALANCE SYNC
    # =========================================================

    def _sync_batch_balances(self, stock_entry):
        """
        Populate Loan Waybill Batch Balance rows from the submitted Stock Entry.
        Handles three Frappe item tracking modes:
          1. Classic batch_no / serial_no on the SE item row
          2. serial_and_batch_bundle (Frappe v15+)
          3. Non-tracked items
        """
        if not stock_entry or not stock_entry.items:
            frappe.throw(_("Stock Entry has no items — cannot sync batch balances."))

        frappe.db.delete("Loan Waybill Batch Balance", {"parent": self.name})

        for d in stock_entry.items:
            # Case 1: classic batch / serial on the row
            if d.batch_no or d.serial_no:
                self._insert_batch_balance_row(
                    item_code=d.item_code,
                    batch_no=d.batch_no,
                    serial_no=d.serial_no,
                    warehouse=d.t_warehouse,
                    qty=d.qty,
                    valuation_rate=d.basic_rate,
                    expiry_date=self._get_tracking_expiry(d.batch_no, d.serial_no),
                )
                continue

            # Case 2: Serial & Batch Bundle (Frappe v15+)
            if d.serial_and_batch_bundle:
                bundle = frappe.get_doc("Serial and Batch Bundle", d.serial_and_batch_bundle)
                for row in bundle.entries:
                    self._insert_batch_balance_row(
                        item_code=d.item_code,
                        batch_no=row.batch_no,
                        serial_no=row.serial_no,
                        warehouse=d.t_warehouse,
                        qty=abs(flt(row.qty)),
                        valuation_rate=d.basic_rate,
                        expiry_date=self._get_tracking_expiry(row.batch_no, row.serial_no),
                    )
                continue

            # Case 3: non-tracked item
            self._insert_batch_balance_row(
                item_code=d.item_code,
                warehouse=d.t_warehouse,
                qty=d.qty,
                valuation_rate=d.basic_rate,
            )

    def _insert_batch_balance_row(
        self,
        item_code,
        warehouse,
        qty,
        valuation_rate=0,
        batch_no=None,
        serial_no=None,
        expiry_date=None,
    ):
        frappe.get_doc(
            {
                "doctype": "Loan Waybill Batch Balance",
                "parent": self.name,
                "parenttype": "Loan Waybill",
                "parentfield": "batch_balances",
                "item_code": item_code,
                "batch_no": batch_no,
                "serial_no": serial_no,
                "warehouse": warehouse,
                "qty_loaned": flt(qty),
                "qty_converted": 0.0,
                "qty_remaining": flt(qty),
                "valuation_rate": flt(valuation_rate),
                "expiry_date": expiry_date,
            }
        ).insert(ignore_permissions=True)

    @staticmethod
    def _get_tracking_expiry(batch_no, serial_no):
        if batch_no:
            return frappe.db.get_value("Batch", batch_no, "expiry_date")
        if serial_no:
            return frappe.db.get_value("Serial No", serial_no, "warranty_expiry_date")
        return None

    # =========================================================
    # CONVERSION HELPERS  (called by delivery_note controller)
    # =========================================================

    def apply_conversion(self, delivery_note_name, items):
        """
        Record a conversion against this Loan Waybill.

        `items` — list of dicts: { item_code, batch_no, serial_no, qty_converted }

        Called by Delivery Note on_submit when
        custom_waybill_type == "Loan Conversion Waybill".
        """
        self.reload()

        # Create conversion history entries for each item
        for row in items:
            item_code = row.get("item_code")
            batch_no = row.get("batch_no") or None
            serial_no = row.get("serial_no") or None
            qty = flt(row.get("qty_converted"))
            if not qty:
                continue

            bb = self._find_batch_balance_row(item_code, batch_no, serial_no)
            if not bb:
                frappe.throw(
                    _(
                        "No matching Batch Balance row for Item {0}, "
                        "Batch {1}, Serial {2} in Loan Waybill {3}."
                    ).format(item_code, batch_no or "—", serial_no or "—", self.name)
                )

            new_converted = flt(bb.qty_converted) + qty
            new_remaining = flt(bb.qty_loaned) - new_converted

            if new_remaining < -0.001:
                frappe.throw(
                    _(
                        "Conversion qty {0} for Item {1} (Batch {2}) exceeds "
                        "remaining loan balance {3} in Loan Waybill {4}."
                    ).format(qty, item_code, batch_no or "—", flt(bb.qty_remaining), self.name)
                )

            frappe.db.set_value(
                "Loan Waybill Batch Balance",
                bb.name,
                {
                    "qty_converted": new_converted,
                    "qty_remaining": max(0.0, new_remaining),
                },
            )

            for item in self.items:
                if item.item_code == item_code:
                    frappe.db.set_value(
                        "Loan Waybill Item",
                        item.name,
                        {
                            "quantity_converted": flt(item.quantity_converted) + qty,
                            "quantity_remaining": max(0.0, flt(item.quantity_remaining) - qty),
                        },
                    )
                    break

        # Create individual conversion history entries for each item
        for row in items:
            item_code = row.get("item_code")
            qty = flt(row.get("qty_converted"))
            if not qty:
                continue

            # Get the delivery note to fetch item details
            dn_doc = frappe.get_doc("Delivery Note", delivery_note_name)
            dn_item = next((d for d in dn_doc.items if d.item_code == item_code), None)
            
            if not dn_item:
                continue

            # Create conversion history entry for this item
            frappe.get_doc(
                {
                    "doctype": "Loan Conversion History",
                    "parent": self.name,
                    "parenttype": "Loan Waybill",
                    "parentfield": "conversion_history",
                    "sales_order": dn_item.against_sales_order,
                    "delivery_note": delivery_note_name,
                    "conversion_date": nowdate(),
                    "item_code": item_code,
                    "description": dn_item.description,
                    "quantity_converted": qty,
                    "batch_no": row.get("batch_no"),
                    "serial_no": row.get("serial_no"),
                }
            ).insert(ignore_permissions=True)

        self.reload()
        self._calculate_totals()
        self._update_conversion_status()
        self.db_update()

    def reverse_conversion(self, delivery_note_name, items):
        """
        Undo a conversion when its Delivery Note is cancelled.
        `items` has the same structure as apply_conversion.
        """
        self.reload()

        for row in items:
            item_code = row.get("item_code")
            batch_no = row.get("batch_no") or None
            serial_no = row.get("serial_no") or None
            qty = flt(row.get("qty_converted"))
            if not qty:
                continue

            bb = self._find_batch_balance_row(item_code, batch_no, serial_no)
            if not bb:
                frappe.throw(
                    _(
                        "Cannot reverse: no Batch Balance row for Item {0}, "
                        "Batch {1} in Loan Waybill {2}."
                    ).format(item_code, batch_no or "—", self.name)
                )

            new_converted = max(0.0, flt(bb.qty_converted) - qty)
            new_remaining = flt(bb.qty_loaned) - new_converted

            frappe.db.set_value(
                "Loan Waybill Batch Balance",
                bb.name,
                {"qty_converted": new_converted, "qty_remaining": new_remaining},
            )

            for item in self.items:
                if item.item_code == item_code:
                    frappe.db.set_value(
                        "Loan Waybill Item",
                        item.name,
                        {
                            "quantity_converted": max(0.0, flt(item.quantity_converted) - qty),
                            "quantity_remaining": flt(item.quantity_remaining) + qty,
                        },
                    )
                    break

        # Remove the conversion history row for this specific delivery note
        history_name = frappe.db.get_value(
            "Loan Conversion History",
            {"parent": self.name, "delivery_note": delivery_note_name},
            "name",
        )
        if history_name:
            frappe.delete_doc(
                "Loan Conversion History", history_name, ignore_permissions=True, force=True
            )

        self.reload()
        self._calculate_totals()
        self._update_conversion_status()
        self.db_update()

    def _find_batch_balance_row(self, item_code, batch_no, serial_no):
        filters = {"parent": self.name, "item_code": item_code}
        if batch_no:
            filters["batch_no"] = batch_no
        elif serial_no:
            filters["serial_no"] = serial_no

        return frappe.db.get_value(
            "Loan Waybill Batch Balance",
            filters,
            ["name", "qty_loaned", "qty_converted", "qty_remaining"],
            as_dict=True,
        )

    # =========================================================
    # CANCEL
    # =========================================================

    def before_cancel(self):
        """
        Single guard: block cancellation when any conversions exist.
        All conversion checks live here — on_cancel assumes this passed cleanly.
        """
        self._calculate_totals()

        has_conversions = flt(self.total_converted_quantity) > 0 or frappe.db.exists(
            "Loan Conversion History", {"parent": self.name}
        )

        if has_conversions:
            frappe.throw(
                _(
                    "Cannot cancel Loan Waybill {0}. Conversions exist. "
                    "Cancel all related Loan Conversion Waybills (Delivery Notes) first."
                ).format(self.name)
            )

    def on_cancel(self):
        """
        Runs only when before_cancel passes (zero conversions).
        Cancels the Stock Entry to return stock to the source warehouse,
        then cleans up batch balance rows.
        """
        self.ignore_linked_doctypes = ["Stock Entry"]
        self._cancel_loan_stock_entry()
        frappe.db.delete("Loan Waybill Batch Balance", {"parent": self.name})
        self.db_set("conversion_status", "Cancelled", update_modified=False)

    def _cancel_loan_stock_entry(self):
        """Cancel the linked SE using the allow-flag to bypass the guard hook."""
        if not self.stock_entry:
            return

        docstatus = frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus")

        if docstatus is None or docstatus == 2:
            self.db_set("stock_entry", None, update_modified=False)
            return

        if docstatus == 1:
            se = frappe.get_doc("Stock Entry", self.stock_entry)
            frappe.flags.allow_cancel_loan_stock_entry = True
            try:
                se.cancel()
            finally:
                frappe.flags.allow_cancel_loan_stock_entry = False

        self.db_set("stock_entry", None, update_modified=False)

    # =========================================================
    # DELETE GUARD
    # =========================================================

    def on_trash(self):
        if self.docstatus == 1:
            frappe.throw(_("Cannot delete a submitted Loan Waybill. Cancel it first."))

        if self.stock_entry:
            se_status = frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus")
            if se_status == 1:
                frappe.throw(
                    _(
                        "Cannot delete Loan Waybill {0} — "
                        "its Stock Entry {1} is still submitted."
                    ).format(self.name, self.stock_entry)
                )


# =========================================================
# WHITELISTED API
# =========================================================


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_items_with_stock(doctype, txt, searchfield, start, page_len, filters):
    """Link-field search: items with actual stock in the given warehouse."""
    warehouse = filters.get("warehouse") if isinstance(filters, dict) else None
    if not warehouse:
        return []

    return frappe.db.sql(
        """
        SELECT item_code
        FROM `tabBin`
        WHERE warehouse = %s
          AND actual_qty > 0
          AND item_code LIKE %s
        ORDER BY item_code
        LIMIT %s, %s
        """,
        (warehouse, f"%{txt}%", start, page_len),
    )


@frappe.whitelist()
def get_pending_loan_waybills(sales_order: str):
    """
    Return all submitted, not-fully-converted Loan Waybills for the SO's customer,
    filtered to batch rows with remaining qty where the SO also has remaining qty.
    Ordered by loan_date ascending (FIFO).
    """
    if not sales_order:
        frappe.throw(_("Sales Order is required."))

    so = frappe.get_doc("Sales Order", sales_order)
    if so.docstatus != 1:
        frappe.throw(_("Sales Order must be submitted."))

    item_codes = {row.item_code for row in so.items}
    so_remaining_map = _get_so_remaining_quantities(sales_order)

    loans = frappe.get_all(
        "Loan Waybill",
        filters={
            "customer": so.customer,
            "docstatus": 1,
            "conversion_status": ["!=", "Fully Converted"],
        },
        fields=["name", "loan_date"],
        order_by="loan_date asc",
    )

    results = []
    for loan in loans:
        batch_rows = frappe.get_all(
            "Loan Waybill Batch Balance",
            filters={"parent": loan.name, "qty_remaining": [">", 0]},
            fields=[
                "item_code", "batch_no", "serial_no", "expiry_date",
                "warehouse", "qty_loaned", "qty_converted", "qty_remaining",
            ],
        )

        matching = []
        for bb in batch_rows:
            if bb.item_code not in item_codes:
                continue
            so_rem = so_remaining_map.get(bb.item_code, 0)
            if so_rem <= 0:
                continue
            max_conv = min(flt(bb.qty_remaining), flt(so_rem))
            if max_conv <= 0:
                continue
            matching.append(
                {
                    "item_code": bb.item_code,
                    "batch_no": bb.batch_no,
                    "serial_no": bb.serial_no,
                    "expiry_date": str(bb.expiry_date) if bb.expiry_date else None,
                    "warehouse": bb.warehouse,
                    "qty_loaned": flt(bb.qty_loaned),
                    "qty_converted": flt(bb.qty_converted),
                    "qty_remaining": flt(bb.qty_remaining),
                    "so_qty_remaining": flt(so_rem),
                    "max_convertible_qty": max_conv,
                }
            )

        if matching:
            results.append(
                {
                    "loan_waybill": loan.name,
                    "loan_date": str(loan.loan_date) if loan.loan_date else None,
                    "items": matching,
                }
            )

    return {"customer": so.customer, "sales_order": sales_order, "loan_waybills": results}


@frappe.whitelist()
def make_delivery_note_from_loan(loan_waybill: str, sales_order: str, items: str):
    """
    Prepare (but do NOT save) a Delivery Note of type "Loan Conversion Waybill".

    items — JSON list of: { item_code, batch_no, serial_no, qty, valuation_rate }

    Returns the unsaved Delivery Note as a dict so the JS can open it in the form
    via frappe.model.sync + frappe.set_route. The user saves and submits it manually.
    On submission the delivery_note controller calls loan_doc.apply_conversion().
    """
    import json

    if isinstance(items, str):
        items = json.loads(items)

    loan_doc = frappe.get_doc("Loan Waybill", loan_waybill)
    if loan_doc.docstatus != 1:
        frappe.throw(_("Loan Waybill must be submitted."))
    if loan_doc.conversion_status == "Fully Converted":
        frappe.throw(_("This Loan Waybill is already fully converted."))

    so_doc = frappe.get_doc("Sales Order", sales_order)
    if so_doc.docstatus != 1:
        frappe.throw(_("Sales Order must be submitted."))

    so_remaining_map = _get_so_remaining_quantities(sales_order)

    # Validate all rows before building the DN
    for row in items:
        item_code = row.get("item_code")
        qty = flt(row.get("qty"))
        batch_no = row.get("batch_no") or None
        serial_no = row.get("serial_no") or None

        if qty <= 0:
            frappe.throw(_("Quantity must be greater than zero for Item {0}.").format(item_code))

        bb = loan_doc._find_batch_balance_row(item_code, batch_no, serial_no)
        if not bb or flt(bb.qty_remaining) < qty:
            frappe.throw(
                _(
                    "Requested qty {0} for Item {1} (Batch {2}) exceeds "
                    "remaining loan balance {3}."
                ).format(qty, item_code, batch_no or "—", flt(bb.qty_remaining) if bb else 0)
            )

        so_rem = so_remaining_map.get(item_code, 0)
        if qty > so_rem:
            frappe.throw(
                _(
                    "Requested qty {0} for Item {1} exceeds remaining "
                    "Sales Order quantity {2}."
                ).format(qty, item_code, so_rem)
            )

    # Build item rows
    dn_items = []
    for row in items:
        item_code = row.get("item_code")
        so_item_name = frappe.db.get_value(
            "Sales Order Item",
            {"parent": sales_order, "item_code": item_code},
            "name",
        )
        dn_items.append(
            {
                "item_code": item_code,
                "qty": flt(row.get("qty")),
                "uom": frappe.db.get_value("Item", item_code, "stock_uom"),
                "warehouse": loan_doc.target_warehouse,
                "batch_no": row.get("batch_no") or None,
                "serial_no": row.get("serial_no") or None,
                "rate": flt(row.get("valuation_rate", 0)),
                "use_serial_batch_fields": 1,
                "against_sales_order": sales_order,
                "so_detail": so_item_name,
            }
        )

    customer_address = (
        frappe.db.get_value("Customer", loan_doc.customer, "customer_primary_address")
        or loan_doc.customer_address
    )

    dn = frappe.get_doc(
        {
            "doctype": "Delivery Note",
            "customer": loan_doc.customer,
            "customer_name": loan_doc.customer_name,
            "posting_date": nowdate(),
            "set_warehouse": loan_doc.target_warehouse,
            "customer_address": customer_address,
            "shipping_address_name": loan_doc.shipping_address_name or customer_address,
            "custom_waybill_type": "Loan Conversion Waybill",
            "custom_source_loan_waybill": loan_waybill,
            "custom_is_conversion": 1,
            "custom_conversion_date": nowdate(),
            "items": dn_items,
        }
    )

    dn.run_method("set_missing_values")
    return dn.as_dict()


# =========================================================
# PRIVATE HELPERS
# =========================================================


def _get_so_remaining_quantities(sales_order: str) -> dict:
    """
    Returns {item_code: remaining_qty} for a Sales Order,
    deducting quantities already delivered by submitted non-return Delivery Notes.
    """
    so_items = frappe.get_all(
        "Sales Order Item",
        filters={"parent": sales_order},
        fields=["item_code", "qty"],
    )
    so_qty_map = {row.item_code: flt(row.qty) for row in so_items}

    delivered = frappe.db.sql(
        """
        SELECT dni.item_code, SUM(dni.qty) AS delivered_qty
        FROM `tabDelivery Note Item` dni
        INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE dn.docstatus = 1
          AND dn.is_return = 0
          AND dni.against_sales_order = %s
        GROUP BY dni.item_code
        """,
        sales_order,
        as_dict=True,
    )
    delivered_map = {row.item_code: flt(row.delivered_qty) for row in delivered}

    return {
        item_code: max(0.0, qty - delivered_map.get(item_code, 0.0))
        for item_code, qty in so_qty_map.items()
    }