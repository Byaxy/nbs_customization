import frappe
from frappe import _


def validate(doc, method):
	if doc.get("custom_analyzer_profile") and doc.get("custom_reagent_specification"):
		frappe.throw(
			_(
				"Item cannot be both an analyzer and a reagent. "
				"Set only one of Analyzer Profile or Reagent Specification."
			)
		)

	if doc.get("custom_analyzer_profile"):
		profile_item = frappe.db.get_value("Analyzer Profile", doc.custom_analyzer_profile, "analyzer_item")
		if profile_item and profile_item != doc.name:
			frappe.throw(
				_("Analyzer Profile {0} is for {1}, not {2}.").format(
					frappe.bold(doc.custom_analyzer_profile),
					frappe.bold(profile_item),
					frappe.bold(doc.name),
				)
			)

	if doc.get("custom_reagent_specification"):
		spec_item = frappe.db.get_value("Reagent Specification", doc.custom_reagent_specification, "item")
		if spec_item and spec_item != doc.name:
			frappe.throw(
				_("Reagent Specification {0} is for {1}, not {2}.").format(
					frappe.bold(doc.custom_reagent_specification),
					frappe.bold(spec_item),
					frappe.bold(doc.name),
				)
			)
