// Copyright (c) 2026, NBS Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.payment_type !== "Receive" || frm.doc.party_type !== "Customer") return;

		if (frm.doc.custom_receipt) {
			frm.add_custom_button(
				__("Receipt"),
				() => frappe.set_route("Form", "Receipt", frm.doc.custom_receipt),
				__("View"),
			);
		} else {
			frm.add_custom_button(
				__("Receipt"),
				() =>
					frappe.model.open_mapped_doc({
						method:
							"nbs_customization.nbs_customization.doctype.receipt.receipt.create_receipt_from_pe",
						frm: frm,
					}),
				__("Create"),
			);
		}
	},
});
