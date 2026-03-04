frappe.ui.form.on("Sales Invoice", {
	refresh: function (frm) {
		// Remove/disable "Waybill" button from Sales Invoice
		if (frm.doc.docstatus === 1) {
			// Find and remove the "Waybill" button
			const make_delivery_note_btn = frm.page.btn_group
				.find(".btn-primary")
				.filter(function () {
					return $(this).text().trim() === "Waybill";
				});

			if (make_delivery_note_btn.length > 0) {
				make_delivery_note_btn.remove();
			}

			// Also check for it in the dropdown menu
			setTimeout(function () {
				$(".dropdown-menu .dropdown-item").each(function () {
					if ($(this).text().trim() === "Waybill") {
						$(this).parent().remove();
					}
				});
			}, 500);
		}
	},
});

// Override the Waybill function to prevent it from working
cur_frm.cscript["Waybill"] = function () {
	frappe.msgprint({
		title: __("Action Not Allowed"),
		message: __(
			"Waybills cannot be created from Sales Invoice. Please create them from Sales Order.",
		),
		indicator: "red",
	});
};
