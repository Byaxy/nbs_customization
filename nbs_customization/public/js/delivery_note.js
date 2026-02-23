frappe.ui.form.on("Delivery Note", {
	custom_waybill_type(frm) {
		if (frm.doc.custom_waybill_type !== "Loan Conversion Waybill") return;

		frm.set_value({
			custom_is_conversion: 1,
		});
	},
});
