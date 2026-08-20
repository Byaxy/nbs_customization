import frappe
from frappe import _


def validate(doc, method):
	if doc.custom_instrument_specification and doc.custom_reagent_specification:
		frappe.throw(
			_("Item cannot be both an instrument and a reagent. "
			  "Set only one of Instrument Specification or Reagent Specification.")
		)

	if doc.custom_instrument_specification:
		spec_item = frappe.db.get_value(
			"Instrument Specification", doc.custom_instrument_specification, "item")
		if spec_item and spec_item != doc.name:
			frappe.throw(
				_("Instrument Specification {0} is for {1}, not {2}.").format(
					frappe.bold(doc.custom_instrument_specification),
					frappe.bold(spec_item),
					frappe.bold(doc.name),
				))

	if doc.custom_reagent_specification:
		spec_item = frappe.db.get_value(
			"Reagent Specification", doc.custom_reagent_specification, "item")
		if spec_item and spec_item != doc.name:
			frappe.throw(
				_("Reagent Specification {0} is for {1}, not {2}.").format(
					frappe.bold(doc.custom_reagent_specification),
					frappe.bold(spec_item),
					frappe.bold(doc.name),
				))
