# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import flt


class LoanWaybill(Document):

    # =========================================================
    # VALIDATION
    # =========================================================

    def validate(self):
        self._validate_no_amend()
        self.validate_warehouses()
        self.validate_stock_availability()
        self.calculate_totals()
        self.update_overall_status()
        self._validate_loan_item_integrity()

    def _validate_no_amend(self):
        if getattr(self, "amended_from", None):
            frappe.throw("Amend is not allowed for Loan Waybills. Cancel and create a new Loan Waybill instead.")

    def validate_warehouses(self):
        if not self.source_warehouse or not self.target_warehouse:
            frappe.throw("Source and Target Warehouse are mandatory.")

        if self.source_warehouse == self.target_warehouse:
            frappe.throw("Source and Target Warehouse cannot be the same.")

        # Ensure target belongs to customer
        if self.customer:
            if self.customer not in self.target_warehouse:
                frappe.throw("Target Warehouse must belong to the selected Customer.")

    def validate_stock_availability(self):
        """
        Ensure source warehouse has enough quantity for each item.
        """
        for item in self.items:
            if not item.item_code or not item.quantity_loaned:
                continue

            actual_qty = frappe.db.get_value(
                "Bin",
                {"item_code": item.item_code, "warehouse": self.source_warehouse},
                "actual_qty",
            ) or 0

            if actual_qty < item.quantity_loaned:
                frappe.throw(
                    f"Insufficient stock for Item {item.item_code} in Warehouse {self.source_warehouse}. "
                    f"Available: {actual_qty}, Requested: {item.quantity_loaned}"
                )

    # =========================================================
    # TOTALS & STATUS
    # =========================================================

    def calculate_totals(self):
        self.total_loan_quantity = 0
        self.total_converted_quantity = 0
        self.total_remaining_quantity = 0

        for item in self.items:
            item.quantity_remaining = flt(item.quantity_loaned) - flt(item.quantity_converted)

            self.total_loan_quantity += flt(item.quantity_loaned)
            self.total_converted_quantity += flt(item.quantity_converted)
            self.total_remaining_quantity += flt(item.quantity_remaining)

    def _validate_loan_item_integrity(self):
        for item in self.items:
            if flt(item.quantity_loaned) != flt(item.quantity_converted) + flt(item.quantity_remaining):
                frappe.throw(
                    f"Invalid quantities for Item {item.item_code}. "
                    "Expected quantity_loaned = quantity_converted + quantity_remaining."
                )

    def update_overall_status(self):
        if self.docstatus == 0:
            self.conversion_status = "Draft"
            return

        if self.docstatus == 2:
            self.conversion_status = "Cancelled"
            return

        fully = all(flt(i.quantity_remaining) == 0 for i in self.items)
        none = all(flt(i.quantity_converted) == 0 for i in self.items)

        if fully:
            self.conversion_status = "Fully Converted"
        elif none:
            self.conversion_status = "Pending"
        else:
            self.conversion_status = "Partially Converted"

    # =========================================================
    # SUBMIT FLOW
    # =========================================================

    def on_submit(self):
        stock_entry = self.create_stock_entry()

        if not stock_entry:
            frappe.throw("Failed to create Stock Entry for Loan Waybill.")

        self.sync_batch_balances_from_stock_entry(stock_entry)
        self._validate_batch_balance_integrity()
        self.calculate_totals()
        self.update_overall_status()
        self._validate_loan_item_integrity()
        self.db_set("conversion_status", "Pending")

    def create_stock_entry(self):
        if self.stock_entry:
            return frappe.get_doc("Stock Entry", self.stock_entry)

        stock_entry = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Transfer",
            "posting_date": self.loan_date,
            "from_warehouse": self.source_warehouse,
            "to_warehouse": self.target_warehouse,
            "custom_is_loan": True,
            "items": []
        })

        for item in self.items:
            stock_entry.append("items", {
                "item_code": item.item_code,
                "qty": item.quantity_loaned,
                "uom": item.uom,
                "s_warehouse": self.source_warehouse,
                "t_warehouse": self.target_warehouse,
                "basic_rate": item.rate,
            })

        stock_entry.insert(ignore_permissions=True)
        stock_entry.submit()

        self.db_set("stock_entry", stock_entry.name)
        return stock_entry

    # =========================================================
    # BATCH BALANCE SYNC ENGINE
    # =========================================================

    def sync_batch_balances_from_stock_entry(self, stock_entry):
        if not stock_entry:
            frappe.throw("Stock Entry not found for batch synchronization.")

        if not stock_entry.items:
            frappe.throw("Stock Entry contains no items to sync batch balances.")

        # delete existing balances (resubmit safety)
        frappe.db.delete(
            "Loan Waybill Batch Balance",
            {"parent": self.name}
        )

        for d in stock_entry.items:

            # ---------------------------------------------------
            # CASE 1: Classic batch / serial directly on row
            # ---------------------------------------------------
            if d.batch_no or d.serial_no:
                expiry_date = None

                if d.batch_no:
                    expiry_date = frappe.db.get_value("Batch", d.batch_no, "expiry_date")

                elif d.serial_no:
                    expiry_date = frappe.db.get_value(
                        "Serial No", d.serial_no, "warranty_expiry_date"
                    )

                frappe.get_doc({
                    "doctype": "Loan Waybill Batch Balance",
                    "parent": self.name,
                    "parenttype": "Loan Waybill",
                    "parentfield": "batch_balances",

                    "item_code": d.item_code,
                    "batch_no": d.batch_no,
                    "serial_no": d.serial_no,
                    "warehouse": d.t_warehouse,

                    "qty_loaned": d.qty,
                    "qty_converted": 0,
                    "qty_remaining": d.qty,

                    "valuation_rate": d.basic_rate,
                    "stock_entry": stock_entry.name,
                    "stock_entry_detail": d.name,
                    "expiry_date": expiry_date
                }).insert(ignore_permissions=True)

                continue

            # ---------------------------------------------------
            # CASE 2: Serial & Batch Bundle (Frappe v16+)
            # ---------------------------------------------------
            if d.serial_and_batch_bundle:

                bundle = frappe.get_doc("Serial and Batch Bundle", d.serial_and_batch_bundle)

                for row in bundle.entries:

                    qty = abs(row.qty)
                    expiry_date = None

                    if row.batch_no:
                        expiry_date = frappe.db.get_value("Batch", row.batch_no, "expiry_date")

                    elif row.serial_no:
                        expiry_date = frappe.db.get_value(
                            "Serial No", row.serial_no, "warranty_expiry_date"
                        )
                    frappe.get_doc({
                        "doctype": "Loan Waybill Batch Balance",
                        "parent": self.name,
                        "parenttype": "Loan Waybill",
                        "parentfield": "batch_balances",

                        "item_code": d.item_code,
                        "batch_no": row.batch_no,
                        "serial_no": row.serial_no,
                        "warehouse": d.t_warehouse,

                        "qty_loaned": qty,
                        "qty_converted": 0,
                        "qty_remaining": qty,

                        "valuation_rate": d.basic_rate,
                        "stock_entry": stock_entry.name,
                        "stock_entry_detail": d.name,
                        "expiry_date": expiry_date
                    }).insert(ignore_permissions=True)

                continue

            # ---------------------------------------------------
            # CASE 3: No tracking at all (non-batch/non-serial item)
            # ---------------------------------------------------
            frappe.get_doc({
                "doctype": "Loan Waybill Batch Balance",
                "parent": self.name,
                "parenttype": "Loan Waybill",
                "parentfield": "batch_balances",

                "item_code": d.item_code,
                "warehouse": d.t_warehouse,

                "qty_loaned": d.qty,
                "qty_converted": 0,
                "qty_remaining": d.qty,

                "valuation_rate": d.basic_rate,
                "stock_entry": stock_entry.name,
                "stock_entry_detail": d.name,
            }).insert(ignore_permissions=True)

    def _validate_batch_balance_integrity(self):
        balances = frappe.get_all(
            "Loan Waybill Batch Balance",
            filters={"parent": self.name},
            fields=[
                "name",
                "item_code",
                "batch_no",
                "serial_no",
                "stock_entry_detail",
                "qty_loaned",
                "qty_converted",
                "qty_remaining",
            ],
        )

        seen = set()
        for b in balances:
            key = (b.item_code, b.batch_no, b.serial_no, b.stock_entry_detail)
            if key in seen:
                frappe.throw(
                    "Duplicate Loan Waybill Batch Balance row detected for "
                    f"Item {b.item_code}, Batch {b.batch_no or '-'}, Serial {b.serial_no or '-'}."
                )
            seen.add(key)

            if flt(b.qty_loaned) != flt(b.qty_converted) + flt(b.qty_remaining):
                frappe.throw(
                    "Invalid Loan Waybill Batch Balance quantities for "
                    f"Item {b.item_code}, Batch {b.batch_no or '-'}, Serial {b.serial_no or '-'}. "
                    "Expected qty_loaned = qty_converted + qty_remaining."
                )

        total_remaining = sum(flt(b.qty_remaining) for b in balances)
        total_converted = sum(flt(b.qty_converted) for b in balances)
        total_loaned = sum(flt(b.qty_loaned) for b in balances)
        if total_loaned != total_remaining + total_converted:
            frappe.throw(
                "Invalid totals in Loan Waybill Batch Balances. "
                "Expected sum(qty_loaned) = sum(qty_remaining) + sum(qty_converted)."
            )

    def _has_conversions(self) -> bool:
        if frappe.db.exists(
            "Loan Conversion History",
            {"parent": self.name},
        ):
            return True

        converted = frappe.db.get_value(
            "Loan Waybill Batch Balance",
            {"parent": self.name, "qty_converted": [">", 0]},
            "name",
        )
        return bool(converted)

    # =========================================================
    # CANCEL FLOW
    # =========================================================

    def before_cancel(self):
        self.calculate_totals()
        self.update_overall_status()

        if flt(self.total_converted_quantity) > 0 or self._has_conversions():
            frappe.throw(
                f"Cannot cancel Loan Waybill {self.name}. "
                "Converted quantity exists. Cancel related Conversion Waybills (Delivery Notes) first."
            )

        if self.stock_entry:
            se = frappe.get_doc("Stock Entry", self.stock_entry)
            if se.docstatus == 1:
                frappe.flags.allow_cancel_loan_stock_entry = True

                se.custom_is_loan = 0
                try:
                    se.cancel()
                finally:
                    frappe.flags.allow_cancel_loan_stock_entry = False

        frappe.db.delete(
            "Loan Waybill Batch Balance",
            {"parent": self.name}
        )

    def on_cancel(self):
        # Check cancellation permissions
        if not frappe.has_permission("Loan Waybill", "cancel", self.name):
            frappe.throw("You do not have permission to cancel Loan Waybills.")
        
        # Prevent cancellation if conversions exist
        if flt(self.total_converted_quantity) > 0 or self._has_conversions():
            frappe.throw(
                f"Cannot cancel Loan Waybill {self.name}. "
                "Converted quantity exists. Cancel related Conversion Waybills first."
            )

        # Only ignore Stock Entry, allow other linked documents to block if needed
        self.ignore_linked_doctypes = ["Stock Entry"]
        
        try:
            # Reverse stock entry (enterprise standard)
            self._reverse_stock_entry()
            
            # Clear batch balances (clean state)
            self._clear_batch_balances()
            
            # Update status
            self.db_set("conversion_status", "Cancelled")
            frappe.msgprint(f"Loan Waybill {self.name} cancelled successfully")
            
        except Exception as e:
            frappe.log_error(f"Loan Waybill cancellation failed: {str(e)}")
            frappe.throw("Cancellation failed. Please check system logs.")

    # =========================================================
    # DELETE SAFETY
    # =========================================================

    def _reverse_stock_entry(self):
        """Cancel original stock entry following ERPNext best practices"""
        if not self.stock_entry:
            # No stock entry to cancel, which is valid for some scenarios
            frappe.msgprint("No Stock Entry found to cancel.")
            return
            
        try:
            # Check if stock entry exists and its status
            se_docstatus = frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus")
            
            if se_docstatus is None:
                # Stock Entry doesn't exist, clear reference
                frappe.msgprint("Stock Entry reference was invalid, clearing reference.")
                self.db_set("stock_entry", None)
                return
                
            if se_docstatus == 2:
                # Stock Entry already cancelled
                frappe.msgprint("Stock Entry was already cancelled.")
                self.db_set("stock_entry", None)
                return
                
            if se_docstatus == 1:
                # Stock Entry is submitted, cancel it
                se = frappe.get_doc("Stock Entry", self.stock_entry)
                se.cancel()  # Standard ERPNext cancellation
                frappe.msgprint(f"Stock Entry {se.name} cancelled successfully")
                
            self.db_set("stock_entry", None)
            
        except Exception as e:
            frappe.log_error(f"Failed to cancel Stock Entry {self.stock_entry}: {str(e)}")
            # Don't re-throw this error - allow cancellation to continue
            frappe.msgprint(f"Warning: Could not cancel Stock Entry {self.stock_entry}, but continuing with Loan Waybill cancellation.")

    def _clear_batch_balances(self):
        """Remove all batch balance records for clean state"""
        try:
            deleted_count = frappe.db.count("Loan Waybill Batch Balance", {"parent": self.name})
            frappe.db.delete("Loan Waybill Batch Balance", {"parent": self.name})
            frappe.msgprint(f"Cleaned up {deleted_count} batch balance records")
        except Exception as e:
            frappe.log_error(f"Failed to clear batch balances: {str(e)}")
            raise

    def on_trash(self):
        # Prevent deletion of submitted Loan Waybills
        if self.docstatus == 1:
            frappe.throw("Cannot delete submitted Loan Waybill. Cancel first.")
        
        # Additional check for stock entry
        if self.stock_entry:
            se = frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus")
            if se == 1:
                frappe.throw(
                    "Cannot delete Loan Waybill with submitted Stock Entry. Cancel first."
                )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_items_with_stock(doctype, txt, searchfield, start, page_len, filters):
    warehouse = filters.get("warehouse")

    if not warehouse:
        return []

    return frappe.db.sql(
        """
        SELECT
            item_code
        FROM `tabBin`
        WHERE warehouse = %s
        AND actual_qty > 0
        AND item_code LIKE %s
        ORDER BY item_code
        LIMIT %s, %s
        """,
        (warehouse, f"%{txt}%", start, page_len),
    )
