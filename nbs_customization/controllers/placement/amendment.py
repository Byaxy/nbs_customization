import frappe


@frappe.whitelist()
def mark_effective(amendment_name):
	doc = frappe.get_doc("Contract Amendment", amendment_name)

	if doc.status != "Approved":
		frappe.throw(
			frappe._("Cannot mark amendment effective — status is '{0}', not 'Approved'.").format(doc.status)
		)

	if doc.effective_date and doc.effective_date > frappe.utils.getdate(frappe.utils.today()):
		frappe.throw(
			frappe._("Cannot mark amendment Effective before its effective date ({0}).").format(
				doc.effective_date
			)
		)

	doc.apply_to_contract()

	return True
