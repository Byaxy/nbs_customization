from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

TEMPLATE = (
	'{% from "nbs_customization/templates/print_formats/macros.html" import sales_invoice_numbers %}'
	'{{ sales_invoice_numbers("SO-TEST", dn) }}'
)
REAL_SQL = frappe.db.sql


def invoice_sql(*responses):
	queue = list(responses)

	def fake_sql(query, *args, **kwargs):
		if "tabSales Invoice" in query or "tabDelivery Note Item" in query:
			return queue.pop(0) if queue else []
		return REAL_SQL(query, *args, **kwargs)

	return fake_sql


class TestPrintSalesInvoiceNumbers(IntegrationTestCase):
	def test_order_wide_renders_each_invoice_on_its_own_line(self):
		with patch.object(frappe.db, "sql", side_effect=invoice_sql(["INV-A", "INV-B"])):
			output = frappe.render_template(TEMPLATE, {"dn": None})

		self.assertEqual(output, "INV-A<br />INV-B")

	def test_delivery_note_uses_direct_invoice_link(self):
		with patch.object(frappe.db, "sql", side_effect=invoice_sql(["INV-A"])):
			output = frappe.render_template(TEMPLATE, {"dn": "DN-TEST"})

		self.assertEqual(output, "INV-A")

	def test_delivery_note_falls_back_to_sales_order_invoices(self):
		with patch.object(frappe.db, "sql", side_effect=invoice_sql([], ["INV-B"])):
			output = frappe.render_template(TEMPLATE, {"dn": "DN-TEST"})

		self.assertEqual(output, "INV-B")

	def test_missing_invoices_render_na(self):
		with patch.object(frappe.db, "sql", side_effect=invoice_sql([])):
			output = frappe.render_template(TEMPLATE, {"dn": None})

		self.assertEqual(output, "N/A")
