frappe.ui.form.on("Revenue Share Statement", {
	refresh(frm) {
		_add_generate_button(frm);
	},
});

function _add_generate_button(frm) {
	frm.add_custom_button(__("Generate for Period"), () => {
		if (!frm.doc.contract || !frm.doc.period) {
			frappe.msgprint(__("Please select a Contract and Period first."));
			return;
		}

		frappe.call({
			method: "nbs_customization.nbs_customization.nbs_customization.doctype.revenue_share_statement.revenue_share_statement.generate_revenue_share_statement",
			args: {
				contract_name: frm.doc.contract,
				period: frm.doc.period,
			},
			freeze: true,
			freeze_message: __("Generating revenue share statement..."),
			callback(r) {
				if (r.message) {
					frm.reload_doc();
					frappe.show_alert({
						message: __("Revenue Share Statement generated: {0}", [r.message]),
						indicator: "green",
					});
				}
			},
		});
	});
}
