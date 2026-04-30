frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		setTimeout(() => {
			frm.page.remove_inner_button(__("Waybill"), __("Create"));
		}, 100);
	},
});
