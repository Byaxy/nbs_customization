frappe.ui.form.on("Ownership Transfer Request", {
	refresh(frm) {
		_add_status_buttons(frm);
	},
});

function _add_status_buttons(frm) {
	const status = frm.doc.status;

	if (status === "Draft") {
		frm.add_custom_button(__("Submit"), () => {
			frm.save("submit");
		});
	}

	if (status === "Pending Finance Review") {
		frm.add_custom_button(__("Approve (Finance)"), () => {
			frappe.confirm(
				__("Confirm finance review approval?"),
				() => {
					frm.set_value("finance_reviewed_by", frappe.session.user);
					frm.set_value("finance_review_date", frappe.datetime.get_today());
					frm.set_value("status", "Pending Legal Review");
					frm.save();
				}
			);
		}, __("Approvals"));
	}

	if (status === "Pending Legal Review") {
		frm.add_custom_button(__("Approve (Legal)"), () => {
			frappe.confirm(
				__("Confirm legal review approval?"),
				() => {
					frm.set_value("legal_reviewed_by", frappe.session.user);
					frm.set_value("legal_review_date", frappe.datetime.get_today());
					frm.set_value("status", "Approved");
					frm.save();
				}
			);
		}, __("Approvals"));
	}

	if (status === "Approved") {
		frm.add_custom_button(__("Complete Transfer"), () => {
			if (!frm.doc.transfer_certificate) {
				frappe.msgprint(__("Transfer Certificate must be attached before completing the transfer."));
				return;
			}

			frappe.confirm(
				__(
					"\u26a0\ufe0f This action is irreversible.\n\n"
					+ "Completing the transfer will:\n"
					+ "- Permanently remove this analyzer from the company's asset books\n"
					+ "- Mark the contract as Fulfilled\n"
					+ "- Transfer ownership to the customer\n\n"
					+ "Continue?"
				),
				() => {
					frappe.call({
						method: "nbs_customization.nbs_customization.nbs_customization.doctype.ownership_transfer_request.ownership_transfer_request.complete_transfer",
						args: { otr_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Completing transfer..."),
						callback(r) {
							if (r.message) {
								frm.reload_doc();
								frappe.show_alert({
									message: __("Transfer completed successfully."),
									indicator: "green",
								});
							}
						},
					});
				}
			);
		}, __("Actions"));
	}
}
