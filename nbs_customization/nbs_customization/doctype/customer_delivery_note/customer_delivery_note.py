# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class CustomerDeliveryNote(Document):

    def before_insert(self):
        """Earliest possible duplicate gate — runs before naming, before validate."""
        self._check_duplicate_sales_order(is_new=True)

    def validate(self):
        self._set_defaults()
        self._validate_sales_order()
        self._sync_from_sales_order()
        self._set_address_displays()

    def before_save(self):
        """Catches SO change on an existing draft."""
        if not self.is_new():
            self._check_duplicate_sales_order(is_new=False)

    def on_submit(self):
        self.db_set("status", "Submitted")

    def on_cancel(self):
        self.ignore_linked_doctypes = ("Sales Order",)
        self.db_set("status", "Cancelled")

    # ------------------------------------------------------------------
    # Duplicate prevention
    # ------------------------------------------------------------------

    def _check_duplicate_sales_order(self, is_new: bool):
        if not self.sales_order:
            return

        if is_new:
            # Doc not in DB yet — query without name exclusion
            existing = frappe.db.sql(
                """
                SELECT name FROM `tabCustomer Delivery Note`
                WHERE sales_order = %s AND docstatus < 2
                LIMIT 1
                """,
                (self.sales_order,),
                as_dict=True,
            )
        else:
            existing = frappe.db.sql(
                """
                SELECT name FROM `tabCustomer Delivery Note`
                WHERE sales_order = %s AND name != %s AND docstatus < 2
                LIMIT 1
                """,
                (self.sales_order, self.name),
                as_dict=True,
            )

        if existing:
            dup = existing[0].name
            frappe.throw(
                f"Sales Order {self.sales_order} is already linked to "
                f'<a href="/app/customer-delivery-note/{dup}" target="_blank">'
                f"Customer Delivery Note {dup}</a>.",
                title="Duplicate Link",
            )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _set_defaults(self):
        if not self.date:
            self.date = nowdate()

    def _validate_sales_order(self):
        if not self.sales_order:
            frappe.throw("Sales Order is required.")

        so = frappe.get_doc("Sales Order", self.sales_order)

        if so.docstatus != 1:
            frappe.throw(f"Sales Order {self.sales_order} must be submitted.")

        if self.customer and self.customer != so.customer:
            frappe.throw("Customer must match the Sales Order customer.")

    def _sync_from_sales_order(self):
        so = frappe.get_doc("Sales Order", self.sales_order)

        self.customer = so.customer
        self.customer_name = so.customer_name
        self.customer_address = (
            getattr(so, "customer_address", None)
            or frappe.db.get_value("Customer", so.customer, "customer_primary_address")
        )
        self.shipping_address_name = (
            getattr(so, "shipping_address_name", None) or self.customer_address
        )

        if not self.customer_address or not self.shipping_address_name:
            frappe.throw(
                "Could not resolve billing/shipping address. "
                "Please set addresses on the Sales Order or Customer."
            )

        so_items = {d.item_code: d for d in so.items if d.item_code}
        if not so_items:
            frappe.throw(f"Sales Order {self.sales_order} has no items.")

        cdn_item_codes = {d.item_code for d in self.items if d.item_code}
        extra = cdn_item_codes - so_items.keys()
        if extra:
            frappe.throw(
                f"Items not in Sales Order {self.sales_order}: {', '.join(extra)}."
            )

        cdn_map = {d.item_code: d for d in self.items if d.item_code}
        changed = False

        for item_code, so_item in so_items.items():
            if item_code in cdn_map:
                row = cdn_map[item_code]
                if row.qty_requested != so_item.qty:
                    row.qty_requested = so_item.qty
                    changed = True
                if row.qty_supplied != so_item.qty:
                    row.qty_supplied = so_item.qty
                    changed = True
                if row.balance_left != 0:
                    row.balance_left = 0
                    changed = True
                if row.description != so_item.description:
                    row.description = so_item.description
                    changed = True
            else:
                self.append("items", {
                    "item_code": item_code,
                    "description": so_item.description,
                    "qty_requested": so_item.qty,
                    "qty_supplied": so_item.qty,
                    "balance_left": 0,
                })
                changed = True

        if changed:
            frappe.msgprint(
                "Items updated to match Sales Order.",
                indicator="blue",
                alert=True,
            )

    def _set_address_displays(self):
        if self.customer_address:
            self.address_display = self._get_address_display(self.customer_address)
        if self.shipping_address_name:
            self.shipping_address = self._get_address_display(self.shipping_address_name)

    def _get_address_display(self, address_name: str) -> str:
        try:
            from frappe.contacts.doctype.address.address import get_address_display
            return get_address_display(address_name) or ""
        except Exception:
            return ""