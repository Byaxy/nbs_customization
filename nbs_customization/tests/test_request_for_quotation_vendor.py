import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from nbs_customization.tests.sales_doubles import COMPANY, ensure_test_item


def _make_supplier(name):
	return (
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": name,
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
				or "All Supplier Groups",
				"supplier_type": "Company",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _make_rfq(suppliers):
	item_code = ensure_test_item()
	uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
	warehouse = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 0}, "name")
	naming_series = next(
		line
		for line in frappe.get_meta("Request for Quotation").get_field("naming_series").options.splitlines()
		if line.strip()
	)

	return frappe.get_doc(
		{
			"doctype": "Request for Quotation",
			"company": COMPANY,
			"transaction_date": today(),
			"naming_series": naming_series,
			"suppliers": [{"supplier": supplier} for supplier in suppliers],
			"items": [
				{
					"item_code": item_code,
					"qty": 1,
					"uom": uom,
					"stock_uom": uom,
					"conversion_factor": 1,
					"warehouse": warehouse,
					"schedule_date": today(),
				}
			],
		}
	).insert()


class TestRequestForQuotationVendor(IntegrationTestCase):
	def test_vendor_tracks_first_supplier(self):
		first = _make_supplier("_Test RFQ Supplier A")
		second = _make_supplier("_Test RFQ Supplier B")

		rfq = _make_rfq([first, second])
		self.assertEqual(rfq.vendor, first)

		rfq.suppliers[0], rfq.suppliers[1] = rfq.suppliers[1], rfq.suppliers[0]
		for idx, row in enumerate(rfq.suppliers, start=1):
			row.idx = idx
		rfq.save()

		self.assertEqual(rfq.vendor, second)
		self.assertEqual(frappe.db.get_value("Request for Quotation", rfq.name, "vendor"), second)
