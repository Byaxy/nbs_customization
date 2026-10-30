import frappe

DEFAULTS = {
	"Sales Invoice": ("Sales Invoice", "NBS Sales Invoice"),
	"Delivery Note": ("Waybill", "NBS Waybill"),
	"Customer Delivery Note": ("Customer Delivery Note", "NBS Customer Delivery Note"),
	"Loan Waybill": ("Loan Waybill", "NBS Loan Waybill"),
	"Promissory Note": ("Promissory Note", "NBS Promissory Note"),
	"Quotation": ("Pro-Forma Invoice", "NBS Pro-Forma Invoice"),
	"Purchase Order": ("Purchase Order", "NBS Purchase Order"),
	"Receipt": ("Receipt", "NBS Receipt"),
	"Request for Quotation": ("Request for Quotation", "NBS Request for Quotation"),
}


def execute():
	for doctype, (old_format, new_format) in DEFAULTS.items():
		if not frappe.db.exists("Print Format", new_format):
			continue

		current = _current_default(doctype)
		if current not in (None, "", old_format, new_format):
			continue
		if current == new_format:
			continue

		_set_default(doctype, new_format)


def _current_default(doctype):
	rows = frappe.get_all(
		"Property Setter",
		filters={
			"doc_type": doctype,
			"property": "default_print_format",
			"doctype_or_field": "DocType",
		},
		fields=["name", "value"],
		limit=1,
	)
	return rows[0].value if rows else None


def _set_default(doctype, value):
	rows = frappe.get_all(
		"Property Setter",
		filters={
			"doc_type": doctype,
			"property": "default_print_format",
			"doctype_or_field": "DocType",
		},
		fields=["name"],
		limit=1,
	)
	if rows:
		frappe.db.set_value(
			"Property Setter",
			rows[0].name,
			"value",
			value,
			update_modified=False,
		)
	else:
		frappe.make_property_setter(
			{
				"doctype": doctype,
				"doctype_or_field": "DocType",
				"property": "default_print_format",
				"value": value,
				"property_type": "Data",
			},
			module="NBS Customization",
		)
	frappe.clear_cache(doctype=doctype)
