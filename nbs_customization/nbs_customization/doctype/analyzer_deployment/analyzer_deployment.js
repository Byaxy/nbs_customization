frappe.ui.form.on("Analyzer Deployment", {
	refresh(frm) {
		_setup_queries(frm);
		_add_status_buttons(frm);
		_add_decommission_button(frm);
	},
});

function _setup_queries(frm) {
	frm.set_query("asset_location", () => ({
		filters: {
			is_group: 0,
		},
	}));
}

function _add_status_buttons(frm) {
	if (frm.doc.__islocal) return;

	const status = frm.doc.deployment_status;

	if (status === "Deployed") {
		frm.add_custom_button(
			__("Send for Service"),
			() => {
				_transition_to(frm, "Under Service");
			},
			__("Status")
		);

		frm.add_custom_button(
			__("Retrieve Analyzer"),
			() => {
				_show_retrieval_dialog(frm, "Temporarily Retrieved");
			},
			__("Status")
		);
	}

	if (status === "Under Service") {
		frm.add_custom_button(
			__("Return from Service"),
			() => {
				_transition_to(frm, "Deployed");
			},
			__("Status")
		);
	}

	if (status === "Temporarily Retrieved") {
		frm.add_custom_button(
			__("Deploy Again"),
			() => {
				_transition_to(frm, "Deployed");
			},
			__("Status")
		);

		frm.add_custom_button(
			__("Permanently Retrieve"),
			() => {
				_show_retrieval_dialog(frm, "Permanently Retrieved");
			},
			__("Status")
		);
	}
}

function _transition_to(frm, new_status) {
	frm.set_value("deployment_status", new_status);
	frm.save();
}

function _add_decommission_button(frm) {
	if (frm.doc.__islocal) return;
	if (frm.doc.deployment_status !== "Permanently Retrieved") return;
	if (!frm.doc.asset) return;

	frm.add_custom_button(
		__("Decommission Analyzer"),
		() => {
			frappe.confirm(
				__(
					"Scrap asset {0} via the native Asset scrap flow? This is terminal and cannot be undone.",
					[frm.doc.asset]
				),
				() => {
					frappe.call({
						method: "nbs_customization.controllers.placement.contract.decommission_analyzer",
						args: { asset_name: frm.doc.asset },
						freeze: true,
						freeze_message: __("Scrapping asset..."),
						callback(r) {
							if (!r.exc) {
								frm.reload_doc();
								frappe.show_alert({
									message: __("Asset {0} scrapped.", [frm.doc.asset]),
									indicator: "green",
								});
							}
						},
					});
				}
			);
		},
		__("Actions")
	);
}

function _show_retrieval_dialog(frm, new_status) {
	const dialog = new frappe.ui.Dialog({
		title: __("Analyzer Retrieval — {0}", [
			new_status === "Permanently Retrieved" ? __("Permanent") : __("Temporary"),
		]),
		fields: [
			{
				fieldname: "retrieval_reason",
				label: __("Retrieval Reason"),
				fieldtype: "Select",
				options: [
					"Contract Breach",
					"Contract Fulfilled",
					"Ownership Transfer",
					"Analyzer Service",
					"Analyzer Upgrade",
					"Customer Request",
					"Contract Expiry",
					"Other",
				],
				reqd: 1,
			},
			{
				fieldname: "condition_at_return",
				label: __("Analyzer Condition at Return"),
				fieldtype: "Select",
				options: ["", "Good", "Damaged", "Needs Repair"],
			},
			{
				fieldname: "retrieval_date",
				label: __("Retrieval Date"),
				fieldtype: "Date",
				default: frappe.datetime.get_today(),
			},
		],
		primary_action_label: __("Confirm Retrieval"),
		primary_action(values) {
			frm.set_value("retrieval_reason", values.retrieval_reason);
			frm.set_value("condition_at_return", values.condition_at_return || null);
			frm.set_value("retrieval_date", values.retrieval_date);
			frm.set_value("deployment_status", new_status);
			frm.save();
			dialog.hide();
		},
	});
	dialog.show();
}
