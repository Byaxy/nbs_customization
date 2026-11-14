frappe.ui.form.on("Analyzer Deployment", {
	refresh(frm) {
		_setup_queries(frm);
		if (!frm.doc.asset_storage_location) {
			_set_company_storage_location(frm);
		}
		_add_actions(frm);
		_apply_status_locks(frm);
		_set_status_indicator(frm);
	},

	asset(frm) {
		_set_company_storage_location(frm);
	},

	deployment_status(frm) {
		_apply_status_locks(frm);
		_set_status_indicator(frm);
	},
});

function _set_company_storage_location(frm) {
	if (!frm.doc.asset) return;

	frappe.db.get_value("Asset", frm.doc.asset, "company").then((r) => {
		const company = r.message && r.message.company;
		if (!company) return;

		frappe.db.get_value("Company", company, "abbr").then((c) => {
			const abbr = c.message && c.message.abbr;
			if (!abbr) return;

			const location = `${abbr} - Store`;
			frappe.db.exists("Location", location).then((exists) => {
				if (exists) {
					frm.set_value("asset_storage_location", location);
				}
			});
		});
	});
}

function _set_status_indicator(frm) {
	const colors = {
		Draft: "gray",
		Deployed: "green",
		"Under Service": "orange",
		"Temporarily Retrieved": "blue",
		"Permanently Retrieved": "red",
	};
	frm.page.set_indicator(
		__(frm.doc.deployment_status),
		colors[frm.doc.deployment_status] || "gray"
	);
}

function _setup_queries(frm) {
	frm.set_query("asset_location", () => ({
		filters: { is_group: 0 },
	}));
}

function _add_actions(frm) {
	if (frm.doc.__islocal) return;

	const status = frm.doc.deployment_status;
	const group = __("Actions");

	if (status === "Draft") {
		frm.add_custom_button(__("Deploy Analyzer"), () => _show_deploy_dialog(frm), group);
	}

	if (status === "Deployed") {
		frm.add_custom_button(
			__("Send for Service"),
			() => _transition_to(frm, "Under Service"),
			group
		);
		frm.add_custom_button(__("Retrieve Analyzer"), () => _show_retrieval_dialog(frm), group);
	}

	if (status === "Under Service") {
		frm.add_custom_button(
			__("Return from Service"),
			() => _transition_to(frm, "Deployed"),
			group
		);
	}

	if (status === "Temporarily Retrieved") {
		frm.add_custom_button(__("Deploy Again"), () => _transition_to(frm, "Deployed"), group);
		frm.add_custom_button(
			__("Start Repossession"),
			() => {
				frappe.new_doc("Repossession Request", {
					contract: frm.doc.contract,
					analyzer_deployment: frm.doc.name,
					asset: frm.doc.asset,
					customer: frm.doc.customer,
					customer_name: frm.doc.customer_name,
					requested_by: frappe.session.user,
					request_date: frappe.datetime.get_today(),
				});
			},
			group
		);
	}

	if (frm.doc.acceptance_document) {
		frm.add_custom_button(
			__("View Acceptance"),
			() => frappe.set_route("Form", "Deployment Acceptance", frm.doc.acceptance_document),
			group
		);
	} else if (["Deployed", "Under Service"].includes(status)) {
		frm.add_custom_button(__("Create Acceptance"), () => _create_acceptance(frm), group);
	}

	if (status === "Permanently Retrieved" && frm.doc.asset) {
		frm.add_custom_button(__("Decommission Analyzer"), () => _decommission(frm), group);
	}

	frm.page.set_inner_btn_group_as_primary(group);
}

function _show_deploy_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Deploy Analyzer"),
		fields: [
			{
				fieldname: "deployment_date",
				label: __("Deployment Date"),
				fieldtype: "Date",
				reqd: 1,
				default: frm.doc.deployment_date || frappe.datetime.get_today(),
			},
			{
				fieldname: "installation_date",
				label: __("Installation Date"),
				fieldtype: "Date",
				default: frm.doc.installation_date || frappe.datetime.get_today(),
			},
			{
				fieldname: "condition_at_deployment",
				label: __("Analyzer Condition at Deployment"),
				fieldtype: "Select",
				options: ["", "New", "Refurbished", "Previously Deployed"],
			},
			{
				fieldname: "installed_by",
				label: __("Installed By"),
				fieldtype: "Link",
				options: "User",
				default: frm.doc.installed_by || frappe.session.user,
			},
			{
				fieldname: "notes",
				label: __("Notes"),
				fieldtype: "Small Text",
			},
		],
		primary_action_label: __("Deploy"),
		primary_action(values) {
			dialog.hide();
			frm.set_value("deployment_date", values.deployment_date);
			frm.set_value("installation_date", values.installation_date);
			frm.set_value("condition_at_deployment", values.condition_at_deployment || null);
			frm.set_value("installed_by", values.installed_by || null);
			if (values.notes) frm.set_value("notes", values.notes);
			frm.set_value("deployment_status", "Deployed");
			frm.save();
		},
	});
	dialog.show();
}

function _transition_to(frm, new_status) {
	frm.set_value("deployment_status", new_status);
	frm.save();
}

function _show_retrieval_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Analyzer Retrieval — Temporary"),
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
			frm.set_value("deployment_status", "Temporarily Retrieved");
			frm.save();
			dialog.hide();
		},
	});
	dialog.show();
}

function _create_acceptance(frm) {
	frappe.new_doc("Deployment Acceptance", {
		deployment: frm.doc.name,
		acceptance_date: frappe.datetime.get_today(),
		accepted_by: frappe.session.user,
	});
}

function _decommission(frm) {
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
}

function _apply_status_locks(frm) {
	const draft = frm.doc.deployment_status === "Draft";
	const retrieved = frm.doc.deployment_status === "Permanently Retrieved";

	const placement_fields = [
		"contract",
		"asset",
		"serial_no",
		"analyzer_pid",
		"analyzer_description",
		"customer",
		"customer_name",
		"customer_site",
		"asset_location",
		"asset_storage_location",
		"deployment_date",
		"installation_date",
		"condition_at_deployment",
		"installed_by",
		"accessories_delivered",
	];
	const retrieval_fields = [
		"retrieval_date",
		"retrieval_reason",
		"condition_at_return",
		"retrieved_by",
		"repossession_request",
		"ownership_transfer_request",
	];
	const service_fields = ["biomedical_engineer", "service_interval_days", "next_service_due"];
	const derived_fields = ["acceptance_document", "acceptance_signed", "acceptance_date"];

	derived_fields.forEach((field) => frm.set_df_property(field, "read_only", 1));
	placement_fields.forEach((field) => frm.set_df_property(field, "read_only", !draft));
	retrieval_fields.forEach((field) => frm.set_df_property(field, "read_only", 1));
	service_fields.forEach((field) => frm.set_df_property(field, "read_only", retrieved));
	frm.set_df_property("deployment_status", "read_only", 1);
}
