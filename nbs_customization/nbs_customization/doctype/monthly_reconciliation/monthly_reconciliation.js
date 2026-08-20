frappe.ui.form.on("Monthly Reconciliation", {
	refresh(frm) {
		_add_generate_button(frm);
		_add_penalty_button(frm);
	},
});

function _add_generate_button(frm) {
	frm.add_custom_button(__("Generate for Period"), () => {
		if (!frm.doc.contract || !frm.doc.period) {
			frappe.msgprint(__("Please select a Contract and Period first."));
			return;
		}

		frappe.call({
			method: "nbs_customization.nbs_customization.nbs_customization.doctype.monthly_reconciliation.monthly_reconciliation.generate_monthly_reconciliation",
			args: {
				contract_name: frm.doc.contract,
				period: frm.doc.period,
			},
			freeze: true,
			freeze_message: __("Generating reconciliation..."),
			callback(r) {
				if (r.message) {
					frm.reload_doc();
					frappe.show_alert({
						message: __("Reconciliation generated: {0}", [r.message]),
						indicator: "green",
					});
				}
			},
		});
	});
}

function _add_penalty_button(frm) {
	if (frm.doc.compliance_status !== "Shortfall") return;
	if (frm.doc.penalty_invoice) return;

	frm.add_custom_button(__("Create Shortfall Penalty Invoice"), () => {
		frappe.call({
			method: "nbs_customization.nbs_customization.nbs_customization.doctype.monthly_reconciliation.monthly_reconciliation.create_penalty_invoice",
			args: { reconciliation_name: frm.doc.name },
			freeze: true,
			callback(r) {
				if (r.message) {
					frm.set_value("penalty_invoice", r.message);
					frm.save();
					frappe.show_alert({
						message: __("Penalty Invoice {0} created.", [r.message]),
						indicator: "green",
					});
				}
			},
		});
	}, __("Actions"));
}
