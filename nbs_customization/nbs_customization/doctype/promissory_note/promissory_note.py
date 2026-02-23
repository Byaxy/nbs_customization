# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

from turtle import color
import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class PromissoryNote(Document):
	def validate(self):
		self._set_defaults()
		self._validate_sales_order()
		self._sync_from_sales_order_and_deliveries()
		self._set_address_displays()
		self._calculate_totals_and_status()

	def on_submit(self):
		self._link_to_sales_order()

	def on_cancel(self):
		# Check cancellation permissions
		if not frappe.has_permission("Promissory Note", "cancel", self.name):
			frappe.throw("You do not have permission to cancel Promissory Notes.")
		
		try:
			self._unlink_from_sales_order()
			self.promissory_note_status = "Cancelled"
			frappe.db.set_value("Promissory Note", self.name, "promissory_note_status", "Cancelled")
			frappe.msgprint(f"Promissory Note {self.name} cancelled successfully.")
		except Exception as e:
			frappe.log_error(f"Promissory Note cancellation failed: {str(e)}")
			frappe.throw("Failed to cancel Promissory Note. Please check system logs.")

	def on_trash(self):
		self._unlink_from_sales_order()

	def _set_defaults(self):
		if not self.date:
			self.date = nowdate()
		if not self.naming_series:
			self.naming_series = "NBSPN-.YYYY./.MM./.####"
		if not self.promissory_note_status:
			self.promissory_note_status = "Pending"

	def _validate_sales_order(self):
		if not self.sales_order:
			frappe.throw("Sales Order is required.")

		so = frappe.get_doc("Sales Order", self.sales_order)
		if so.docstatus != 1:
			frappe.throw("Sales Order must be submitted.")

		if self.customer and self.customer != so.customer:
			frappe.throw("Customer must match the Sales Order customer.")

	def _sync_from_sales_order_and_deliveries(self):
		so = frappe.get_doc("Sales Order", self.sales_order)

		self.customer = so.customer
		self.customer_name = so.customer_name

		if hasattr(so, "customer_address") and so.customer_address:
			self.customer_address = so.customer_address
		if hasattr(so, "shipping_address_name") and so.shipping_address_name:
			self.shipping_address_name = so.shipping_address_name

		so_items = [d for d in so.items if d.item_code]
		if not so_items:
			frappe.throw("Sales Order has no items.")

		delivered_by_item = self._get_delivered_qty_by_item_code()

		self.set("items", [])
		for d in so_items:
			so_qty = flt(d.qty)
			delivered_qty = flt(delivered_by_item.get(d.item_code))
			qty_remaining = max(0.0, so_qty - delivered_qty)
			rate = flt(getattr(d, "rate", 0))

			self.append(
				"items",
				{
					"item_code": d.item_code,
					"item_description": d.description,
					"qty_remaining": qty_remaining,
					"unit_price": rate,
					"sub_total": qty_remaining * rate,
					"uom": d.uom,
				},
			)

	def _get_delivered_qty_by_item_code(self) -> dict[str, float]:
		# Sum quantities from submitted Delivery Notes against this Sales Order.
		rows = frappe.db.sql(
			"""
			select dni.item_code, sum(dni.qty) as qty
			from `tabDelivery Note Item` dni
			inner join `tabDelivery Note` dn on dn.name = dni.parent
			where dn.docstatus = 1
			  and ifnull(dni.against_sales_order, '') = %s
			group by dni.item_code
			""",
			(self.sales_order,),
			as_dict=True,
		)
		return {r.item_code: flt(r.qty) for r in rows}

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

		# Pending means nothing delivered: remaining equals SO qty for all items.
		# We infer this by checking if total delivered is 0 (i.e. remaining == so qty).
		delivered_by_item = self._get_delivered_qty_by_item_code()
		nothing_delivered = all(flt(delivered_by_item.get(d.item_code)) == 0 for d in self.items)

		if not any_remaining:
			self.promissory_note_status = "Fulfilled"
		elif nothing_delivered:
			self.promissory_note_status = "Pending"
		else:
			self.promissory_note_status = "Partially Fulfilled"

	def _set_address_displays(self):
		if self.customer_address:
			self.address_display = self._get_address_display(self.customer_address)
		if self.shipping_address_name:
			self.shipping_address = self._get_address_display(self.shipping_address_name)

	def _get_address_display(self, address_name: str) -> str:
		try:
			from frappe.contacts.doctype.address.address import get_address_display
		except Exception:
			return ""

		try:
			return get_address_display(address_name) or ""
		except Exception:
			return ""

	def _link_to_sales_order(self):
		if not self.sales_order:
			return

		frappe.db.set_value(
			"Sales Order",
			self.sales_order,
			{
				"custom_has_promissory_note": 1,
			},
		)

	def _unlink_from_sales_order(self):
		if not self.sales_order:
			return

		current = frappe.db.get_value("Sales Order", self.sales_order, "custom_promissory_note")
		if current != self.name:
			return

		frappe.db.set_value(
			"Sales Order",
			self.sales_order,
			{
				"custom_promissory_note": None,
				"custom_has_promissory_note": 0,
			},
		)


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
		pn = frappe.get_doc("Promissory Note", pn_name)
		
		# Force recalculation by calling the sync and calculate methods directly
		pn._sync_from_sales_order_and_deliveries()
		pn._calculate_totals_and_status()
		
		# Update the database directly to ensure changes persist
		frappe.db.set_value(
			"Promissory Note",
			pn_name,
			{
				"total_amount": pn.total_amount,
				"promissory_note_status": pn.promissory_note_status,
			},
			update_modified=False,
		)
		
		# Update existing child table items instead of deleting and recreating
		existing_items = frappe.db.get_all("Promissory Note Item", 
			filters={"parent": pn_name}, 
			fields=["name", "item_code"]
		)
		
		# Create a mapping of existing items by item_code
		existing_items_map = {item.item_code: item.name for item in existing_items}
		
		for item in pn.items or []:
			if item.item_code in existing_items_map:
				# Update existing item
				frappe.db.set_value("Promissory Note Item", existing_items_map[item.item_code], {
					"qty_remaining": item.qty_remaining,
					"sub_total": item.sub_total,
					"unit_price": item.unit_price
				})
		
	except Exception as e:
		frappe.log_error(
			f"Failed to recalculate Promissory Note {pn_name} for Sales Order {sales_order}: {str(e)}",
			"Promissory Note Recalculation Error"
		)
