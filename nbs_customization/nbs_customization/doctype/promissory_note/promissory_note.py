# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class PromissoryNote(Document):

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def before_insert(self):
        """Hard duplicate gate — runs before naming, before validate."""
        self._check_duplicate_sales_order(is_new=True)

    def before_save(self):
        """Catches SO change on an existing draft."""
        if not self.is_new():
            self._check_duplicate_sales_order(is_new=False)

    def validate(self):
        self._set_defaults()
        self._validate_sales_order()
        self._set_address_displays()

    def on_submit(self):
        self.db_set("promissory_note_status", self.promissory_note_status)

    def on_cancel(self):
        # ERPNext pattern: ignore_linked_doctypes prevents SO from blocking cancel
        self.ignore_linked_doctypes = ("Sales Order",)
        self.db_set("promissory_note_status", "Cancelled")

    def on_trash(self):
        pass  # Relationship is queried dynamically — nothing to clean up

    # ------------------------------------------------------------------
    # Duplicate prevention
    # ------------------------------------------------------------------

    def _check_duplicate_sales_order(self, is_new: bool):
        if not self.sales_order:
            return

        if is_new:
            existing = frappe.db.sql(
                """
                SELECT name FROM `tabPromissory Note`
                WHERE sales_order = %s AND docstatus < 2
                LIMIT 1
                """,
                (self.sales_order,),
                as_dict=True,
            )
        else:
            existing = frappe.db.sql(
                """
                SELECT name FROM `tabPromissory Note`
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
                f'<a href="/app/promissory-note/{dup}" target="_blank">'
                f"Promissory Note {dup}</a>.",
                title="Duplicate Link",
            )

    # ------------------------------------------------------------------
    # Defaults & validation
    # ------------------------------------------------------------------

    def _set_defaults(self):
        if not self.date:
            self.date = nowdate()
        if not self.promissory_note_status:
            self.promissory_note_status = "Pending"

    def _validate_sales_order(self):
        if not self.sales_order:
            frappe.throw("Sales Order is required for Promissory Note.")

        so = frappe.get_doc("Sales Order", self.sales_order)

        if so.docstatus != 1:
            frappe.throw(f"Sales Order {self.sales_order} must be submitted.")

        if self.customer and self.customer != so.customer:
            frappe.throw("Customer must match the Sales Order customer.")

    # ------------------------------------------------------------------
    # Core sync: SO + deliveries → PN items
    # ------------------------------------------------------------------

    def _sync_from_sales_order_and_deliveries(self):
        so = frappe.get_doc("Sales Order", self.sales_order)

        # Always sync header from SO
        self.customer = so.customer
        self.customer_name = so.customer_name
        self.customer_address = (
            getattr(so, "customer_address", None)
            or frappe.db.get_value("Customer", so.customer, "customer_primary_address")
        )
        self.shipping_address_name = (
            getattr(so, "shipping_address_name", None) or self.customer_address
        )

        so_items = [d for d in so.items if d.item_code]
        if not so_items:
            frappe.throw(f"Sales Order {self.sales_order} has no items.")

        delivered_by_item = self._get_delivered_qty_by_item_code()

        # Differential sync: preserve existing rows, only update quantities
        cdn_map = {d.item_code: d for d in self.items if d.item_code}
        so_item_codes = {d.item_code for d in so_items}

        # Remove rows not in SO
        extra = [d for d in self.items if d.item_code not in so_item_codes]
        for row in extra:
            self.remove(row)

        changed = False
        for so_item in so_items:
            delivered_qty = flt(delivered_by_item.get(so_item.item_code))
            qty_remaining = max(0.0, flt(so_item.qty) - delivered_qty)
            rate = flt(getattr(so_item, "rate", 0))
            sub_total = qty_remaining * rate

            if so_item.item_code in cdn_map:
                row = cdn_map[so_item.item_code]
                if (
                    row.qty_remaining != qty_remaining
                    or row.unit_price != rate
                    or row.sub_total != sub_total
                    or row.description != so_item.description
                    or row.uom != so_item.uom
                ):
                    row.qty_remaining = qty_remaining
                    row.unit_price = rate
                    row.sub_total = sub_total
                    row.description = so_item.description
                    row.uom = so_item.uom
                    changed = True
            else:
                self.append("items", {
                    "item_code": so_item.item_code,
                    "description": so_item.description,
                    "qty_remaining": qty_remaining,
                    "unit_price": rate,
                    "sub_total": sub_total,
                    "uom": so_item.uom,
                })
                changed = True

        if changed:
            frappe.msgprint(
                "Items updated from Sales Order and deliveries.",
                indicator="blue",
                alert=True,
            )

    def _get_delivered_qty_by_item_code(self) -> dict[str, float]:
        """
        Sum delivered qty from submitted Delivery Notes against this SO.
        Uses `against_sales_order` on Delivery Note Item — the ERPNext-native
        field that links DN items back to their source SO.
        """
        rows = frappe.db.sql(
            """
            SELECT dni.item_code, SUM(dni.qty) AS qty
            FROM `tabDelivery Note Item` dni
            INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
            WHERE dn.docstatus = 1
              AND dn.is_return = 0
              AND IFNULL(dni.against_sales_order, '') = %s
            GROUP BY dni.item_code
            """,
            (self.sales_order,),
            as_dict=True,
        )
        return {r.item_code: flt(r.qty) for r in rows}

    # ------------------------------------------------------------------
    # Totals & status
    # ------------------------------------------------------------------

    def _calculate_totals_and_status(self):
        total = 0.0
        any_remaining = False

        for d in self.items:
            qty_remaining = flt(d.qty_remaining)
            rate = flt(d.unit_price)
            d.sub_total = qty_remaining * rate
            total += flt(d.sub_total)
            if qty_remaining > 0:
                any_remaining = True

        self.total_amount = total

        if not self.items:
            self.promissory_note_status = "Pending"
            return

        delivered_by_item = self._get_delivered_qty_by_item_code()
        nothing_delivered = all(
            flt(delivered_by_item.get(d.item_code)) == 0 for d in self.items
        )

        if not any_remaining:
            self.promissory_note_status = "Fulfilled"
        elif nothing_delivered:
            self.promissory_note_status = "Pending"
        else:
            self.promissory_note_status = "Partially Fulfilled"

    # ------------------------------------------------------------------
    # Address helpers
    # ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Called from Delivery Note hooks (on_submit + on_cancel)
# ------------------------------------------------------------------

def recalculate_promissory_note_for_sales_order(sales_order: str):
	if not sales_order:
		return

	pn_name = frappe.db.get_value(
		"Promissory Note",
		{"sales_order": sales_order, "docstatus": ["<", 2]},
		"name",
	)
	if not pn_name:
		return

	try:
		# Get accurate delivered qty from Sales Order items
		so_items = frappe.db.sql(
			"""
			SELECT
				soi.item_code,
				soi.qty AS so_qty,
				soi.delivered_qty AS delivered_qty_on_so_item,
				soi.rate,
				soi.description,
				soi.uom
			FROM `tabSales Order Item` soi
			WHERE soi.parent = %s
			""",
			(sales_order,),
			as_dict=True,
		)
		
		# Get existing Promissory Note items for updates
		existing_items = frappe.db.get_all("Promissory Note Item", 
			filters={"parent": pn_name}, 
			fields=["name", "item_code"]
		)
		existing_items_map = {item.item_code: item.name for item in existing_items}
		
		# Calculate totals and determine status
		total_amount = 0.0
		any_remaining = False
		nothing_delivered = True
		
		# Update each Promissory Note item based on Sales Order data
		so_item_codes = {d.item_code for d in so_items}
		updated_items = set()
		
		for so_item in so_items:
			delivered_qty = flt(so_item.delivered_qty_on_so_item)
			qty_remaining = max(0.0, flt(so_item.so_qty) - delivered_qty)
			rate = flt(so_item.rate or 0)
			sub_total = qty_remaining * rate
			
			if qty_remaining > 0:
				any_remaining = True
			if delivered_qty > 0:
				nothing_delivered = False
			
			total_amount += sub_total
			
			if so_item.item_code in existing_items_map:
				# Update existing item
				frappe.db.set_value("Promissory Note Item", existing_items_map[so_item.item_code], {
					"qty_remaining": qty_remaining,
					"sub_total": sub_total,
					"unit_price": rate,
					"description": so_item.description,
					"uom": so_item.uom
				}, update_modified=False)
				updated_items.add(so_item.item_code)
			else:
				# Create new item
				new_item = frappe.db.insert({
					"doctype": "Promissory Note Item",
					"parent": pn_name,
					"parenttype": "Promissory Note",
					"parentfield": "items",
					"item_code": so_item.item_code,
					"description": so_item.description,
					"qty_remaining": qty_remaining,
					"unit_price": rate,
					"sub_total": sub_total,
					"uom": so_item.uom,
				}, ignore_permissions=True)
				updated_items.add(so_item.item_code)
		
		# Remove items that are no longer in the Sales Order
		for item_code, item_name in existing_items_map.items():
			if item_code not in so_item_codes:
				frappe.delete_doc("Promissory Note Item", item_name, ignore_permissions=True)
		
		# Determine status
		if not so_items:
			status = "Pending"
		elif not any_remaining:
			status = "Fulfilled"
		elif nothing_delivered:
			status = "Pending"
		else:
			status = "Partially Fulfilled"
		
		# Update main Promissory Note document
		frappe.db.set_value(
			"Promissory Note",
			pn_name,
			{
				"total_amount": total_amount,
				"promissory_note_status": status,
			},
			update_modified=False,
		)
		
		# Success notification
		frappe.msgprint(
			f"Promissory Note {pn_name} recalculated successfully. "
			f"Status: {status}, Total Amount: {total_amount}",
			alert=True,
			indicator="green"
		)
		
	except Exception as e:
		frappe.log_error(
			f"Failed to recalculate Promissory Note {pn_name} for Sales Order {sales_order}: {str(e)}",
			"Promissory Note Recalculation Error"
		)