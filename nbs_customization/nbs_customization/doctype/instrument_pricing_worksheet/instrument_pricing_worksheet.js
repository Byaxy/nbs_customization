frappe.ui.form.on("Instrument Pricing Worksheet", {
	refresh(frm) {
		_setup_queries(frm);
		_add_apply_button(frm);
		frm.trigger("update_indicators");
		_customize_submit_message(frm);
	},

	update_indicators(frm) {
		const STATUSES = {
			Draft: "orange",
			Approved: "green",
			"Applied to Contract": "purple",
			Cancelled: "red",
		};
		const color = STATUSES[frm.doc.status] || "gray";
		frm.page.set_indicator(__(frm.doc.status), color);
	},

	analyzer_pid(frm) {
		_update_analyzer_type(frm);
		_refresh_reagent_queries(frm);
		_warn_existing_lines(frm);
		_fetch_analyzer_landed_cost(frm);
	},

	contract_type(frm) {
		_auto_set_calculation_output(frm);
	},
});

frappe.ui.form.on("Worksheet Test Reagent Line", {
	item_code(frm, cdt, cdn) {
		_fetch_reagent_details(frm, cdt, cdn);
	},
	monthly_test_volume(frm, cdt, cdn) {
		_update_total_tests(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Worksheet Consumable Line", {
	item_code(frm, cdt, cdn) {
		_fetch_consumable_details(frm, cdt, cdn);
	},
});

function _setup_queries(frm) {
	frm.set_query("analyzer_pid", () => ({
		filters: {
			custom_is_placement_item: 1,
			custom_instrument_specification: ["!=", ""],
		},
	}));

	_refresh_reagent_queries(frm);
}

function _refresh_reagent_queries(frm) {
	if (!frm.doc.analyzer_pid) return;

	frm.set_query("item_code", "reagent_lines", () => ({
		query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
		filters: { analyzer_item: frm.doc.analyzer_pid, reagent_role: "Test Reagent" },
	}));

	frm.set_query("item_code", "consumable_lines", () => ({
		query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
		filters: { analyzer_item: frm.doc.analyzer_pid, reagent_role: "Non-Test Consumable" },
	}));
}

function _update_analyzer_type(frm) {
	if (!frm.doc.analyzer_pid) return;

	frappe.call({
		method: "frappe.client.get_value",
		args: {
			doctype: "Instrument Specification",
			filters: { item: frm.doc.analyzer_pid },
			fieldname: "analyzer_type",
		},
		callback(r) {
			if (r.message) {
				frm.set_value("analyzer_type", r.message.analyzer_type);
			}
		},
	});
}

function _warn_existing_lines(frm) {
	const old = frm.doc.analyzer_pid;
	if (!old) return;

	const lines = (frm.doc.reagent_lines || []).length + (frm.doc.consumable_lines || []).length;
	if (lines > 0) {
		frappe.show_alert({
			message: __(
				"Analyzer changed. Please verify that existing costing lines are still valid.",
			),
			indicator: "orange",
		});
	}
}

function _auto_set_calculation_output(frm) {
	if (frm.doc.contract_type === "CPT") {
		frm.set_value("calculation_output_type", "Revenue Share Percentage");
	} else if (["RRA", "RLO"].includes(frm.doc.contract_type)) {
		frm.set_value("calculation_output_type", "Markup Factor on Reagent Price");
	}
}

function _add_apply_button(frm) {
	const $btn = frm.add_custom_button(__("Apply to Contract"), () => {
		const d = new frappe.ui.Dialog({
			title: __("Apply Worksheet to Contract"),
			fields: [
				{
					fieldname: "asset",
					label: __("Asset"),
					fieldtype: "Link",
					options: "Asset",
					reqd: 1,
					get_query() {
						return {
							filters: {
								custom_current_deployment_status: "Warehouse",
								custom_current_placement_contract: ["is", "not set"],
							},
						};
					},
				},
				{
					fieldname: "customer_site",
					label: __("Customer Site"),
					fieldtype: "Link",
					options: "Address",
					reqd: 1,
					get_query() {
						return {
							query: "frappe.contacts.doctype.address.address.address_query",
							filters: {
								link_doctype: "Customer",
								link_name: frm.doc.customer,
							},
						};
					},
				},
			],
			primary_action({ asset, customer_site }) {
				d.hide();
				frappe.call({
					method: "apply_worksheet_to_contract",
					doc: frm.doc,
					args: {
						asset: asset,
						customer_site: customer_site,
					},
					freeze: true,
					freeze_message: __("Creating contract..."),
					callback(r) {
						if (r.message) {
							frappe.set_route("Form", "Instrument Placement Contract", r.message);
						}
					},
				});
			},
		});
		d.show();
	});
	_toggle_apply_button(frm, $btn);
}

function _toggle_apply_button(frm, $btn) {
	$btn.toggle(frm.doc.docstatus === 1 && !frm.doc.linked_contract);
}

function _fetch_reagent_details(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;

	frappe.call({
		method: "frappe.client.get_value",
		args: {
			doctype: "Reagent Specification",
			filters: { item: row.item_code },
			fieldname: [
				"default_pack_volume_ml",
				"default_tests_per_pack",
				"default_cogs_per_pack",
			],
		},
		callback(r) {
			if (!r.message) return;
			const spec = r.message;
			frappe.model.set_value(cdt, cdn, "pack_volume_ml", spec.default_pack_volume_ml);
			frappe.model.set_value(cdt, cdn, "tests_per_pack", spec.default_tests_per_pack);
			frappe.model.set_value(cdt, cdn, "cogs_per_pack", spec.default_cogs_per_pack);
		},
	});
}

function _fetch_consumable_details(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;

	frappe.call({
		method: "frappe.client.get_value",
		args: {
			doctype: "Reagent Specification",
			filters: { item: row.item_code },
			fieldname: [
				"default_consumption_qty",
				"default_consumption_frequency",
				"default_cogs_per_unit",
			],
		},
		callback(r) {
			if (!r.message) return;
			const spec = r.message;
			frappe.model.set_value(cdt, cdn, "consumption_qty", spec.default_consumption_qty);
			frappe.model.set_value(cdt, cdn, "consumption_frequency", spec.default_consumption_frequency);
			frappe.model.set_value(cdt, cdn, "cogs_per_unit", spec.default_cogs_per_unit);
		},
	});
}

function _update_total_tests(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (row.monthly_test_volume && frm.doc.contract_years) {
		const total = row.monthly_test_volume * 12 * frm.doc.contract_years;
		frappe.model.set_value(cdt, cdn, "total_tests_over_term", total);
	}
}

function _fetch_analyzer_landed_cost(frm) {
	if (!frm.doc.analyzer_pid) return;

	frappe.call({
		method: "frappe.client.get_value",
		args: {
			doctype: "Item",
			filters: { name: frm.doc.analyzer_pid },
			fieldname: "last_purchase_rate",
		},
		callback(r) {
			if (r.message && r.message.last_purchase_rate > 0) {
				frm.set_value("analyzer_landed_cost", r.message.last_purchase_rate);
				return;
			}

			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Item Price",
					filters: {
						item_code: frm.doc.analyzer_pid,
						price_list: "Standard Buying",
					},
					fieldname: "price_list_rate",
				},
				callback(r2) {
					if (r2.message?.price_list_rate) {
						frm.set_value("analyzer_landed_cost", r2.message.price_list_rate);
					}
				},
			});
		},
	});
}

function _customize_submit_message(frm) {
	if (
		frm.doc.docstatus === 0 &&
		!frm.is_new() &&
		frm.meta.is_submittable &&
		frm.perm[0] &&
		frm.perm[0].submit
	) {
		frm.dashboard.clear_comment();
		frm.dashboard.add_comment(__("Submit this document to Approve"), "blue", true);
	}
}
