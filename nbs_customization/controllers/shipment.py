import frappe
from frappe import _


def validate(doc, method=None):
	"""Enforce 1-to-1 relationship: each Delivery Note may only belong to one Shipment."""
	for row in doc.shipment_delivery_note:
		if not row.delivery_note:
			continue

		existing_shipment = frappe.db.get_value(
			"Shipment Delivery Note",
			{
				"delivery_note": row.delivery_note,
				"parent": ["!=", doc.name],
			},
			"parent",
		)

		if existing_shipment:
			frappe.throw(
				_(
					"Delivery Note {0} is already linked to Shipment {1}. "
					"Each Delivery Note can only belong to one Shipment."
				).format(
					frappe.bold(row.delivery_note),
					frappe.bold(existing_shipment),
				)
			)
