frappe.ui.form.on("Repossession Request", {
	refresh(frm) {
		_add_status_buttons(frm);
	},
});

function _add_status_buttons(frm) {
	const status = frm.doc.status;

	if (status === "Draft") {
		frm.add_custom_button(__("Submit for Approval"), () => {
			frm.save("submit");
		});
	}

	if (status === "Pending Approval") {
		frm.add_custom_button(__("Approve"), () => {
			frappe.confirm(
				__("Are you sure you want to approve this repossession request? This authorizes the physical retrieval of the analyzer."),
				() => {
					frm.set_value("status", "Approved");
					frm.set_value("approved_by", frappe.session.user);
					frm.set_value("approval_date", frappe.datetime.get_today());
					frm.save();
				}
			);
		}, __("Actions"));

		frm.add_custom_button(__("Reject"), () => {
			frm.set_value("status", "Closed");
			frm.save();
		}, __("Actions"));
	}

	if (status === "Approved") {
		frm.add_custom_button(__("Execute Retrieval"), () => {
			frappe.confirm(
				__("This will execute the analyzer retrieval. The Analyzer Deployment will be updated to 'Permanently Retrieved'. Continue?"),
				() => {
					frappe.call({
						method: "nbs_customization.nbs_customization.nbs_customization.doctype.repossession_request.repossession_request.execute_retrieval",
						args: { repossession_request_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Executing retrieval..."),
						callback(r) {
							if (r.message) {
								frm.reload_doc();
								frappe.show_alert({
									message: __("Retrieval completed. Deployment: {0}", [r.message]),
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
