import frappe

from nbs_customization.tasks import _apply_amendment_to_contract


@frappe.whitelist()
def mark_effective(amendment_name):
	doc = frappe.get_doc("Contract Amendment", amendment_name)

	if doc.status != "Approved":
		frappe.throw(
			frappe._(
				"Cannot mark amendment effective — status is '{0}', not 'Approved'."
			).format(doc.status)
		)

	_apply_amendment_to_contract(doc)

	return True
