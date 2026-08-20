frappe.ui.form.on("Contract Amendment", {
	refresh(frm) {
		_add_approve_button(frm);
		_add_mark_effective_button(frm);
	},
});

function _add_approve_button(frm) {
	if (frm.doc.status !== "Pending Customer Signature") return;

	frm.add_custom_button(__("Approve Amendment"), () => {
		frappe.confirm(
			__("Are you sure you want to approve this amendment? The new terms will take effect on {0}.",
				[frm.doc.effective_date]),
			() => {
				frm.set_value("status", "Approved");
				frm.set_value("approved_by", frappe.session.user);
				frm.save();
			}
		);
	}, __("Actions"));
}

function _add_mark_effective_button(frm) {
	if (frm.doc.status !== "Approved") return;

	const today = frappe.datetime.get_today();
	const effective = frm.doc.effective_date;
	const is_eligible = effective && effective <= today;

	frm.add_custom_button(__("Mark Effective"), () => {
		frappe.call({
			method: "nbs_customization.controllers.placement.amendment.mark_effective",
			args: { amendment_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Applying amendment to contract..."),
			callback(r) {
				if (r.message) {
					frm.reload_doc();
					frappe.show_alert({
						message: __("Amendment is now effective. Contract terms updated."),
						indicator: "green",
					});
				}
			},
		});
	}, __("Actions"));

	if (!is_eligible) {
		frm.set_df_property("_mark_effective_btn", "disabled", true);
		frm.set_df_property("_mark_effective_btn", "label",
			effective
				? __("Mark Effective (available after {0})", [effective])
				: __("Mark Effective (requires an effective date)"));
	}
}
