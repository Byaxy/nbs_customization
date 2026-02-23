# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate

class CustomerDeliveryNote(Document):
	def validate(self):
		self._set_defaults()
		self._validate_sales_order()
		self._sync_from_sales_order()
		self._set_address_displays()

	def on_submit(self):
		self._link_to_sales_order()

	def on_cancel(self):
		# Check cancellation permissions
		if not frappe.has_permission("Customer Delivery Note", "cancel", self.name):
			frappe.throw("You do not have permission to cancel Customer Delivery Notes.")
			
		try:
			self._unlink_from_sales_order()
			frappe.msgprint(f"Customer Delivery Note {self.name} cancelled successfully.")
		except Exception as e:
			frappe.log_error(f"Customer Delivery Note cancellation failed: {str(e)}")
			frappe.throw("Failed to cancel Customer Delivery Note. Please check system logs.")

	def on_trash(self):
		self._unlink_from_sales_order()

	def on_update_after_submit(self):
		frappe.throw("Customer Delivery Note cannot be modified after submission.")

	def _set_defaults(self):
		if not self.date:
			self.date = nowdate()
		if not self.naming_series:
			self.naming_series = "NBSDN-.YYYY./.MM./.####"

	def _validate_sales_order(self):
		if not self.sales_order:
			frappe.throw("Sales Order is required.")

		so = frappe.get_doc("Sales Order", self.sales_order)
		if so.docstatus != 1:
			frappe.throw("Sales Order must be submitted.")

		if self.customer and self.customer != so.customer:
			frappe.throw("Customer must match the Sales Order customer.")

	def _sync_from_sales_order(self):
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

		# This document is an accounts trigger derived purely from the Sales Order.
		# Always enforce: qty_supplied == qty_requested == Sales Order qty.
		self.set("items", [])
		for d in so_items:
			self.append(
				"items",
				{
					"item_code": d.item_code,
					"item_description": d.description,
					"qty_requested": d.qty,
					"qty_supplied": d.qty,
					"balance_left": 0,
				},
			)

	def _set_address_displays(self):
		# Populate read-only display fields if the Address links are set.
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
				"custom_has_customer_delivery_note": 1,
			},
		)

	def _unlink_from_sales_order(self):
		if not self.sales_order:
			return

		current = frappe.db.get_value(
			"Sales Order", self.sales_order, "custom_customer_delivery_note"
		)
		if current != self.name:
			return

		frappe.db.set_value(
			"Sales Order",
			self.sales_order,
			{
				"custom_customer_delivery_note": None,
				"custom_has_customer_delivery_note": 0,
			},
		)
