frappe.ui.form.on("Instrument Pricing Worksheet", {
	refresh(frm) {
		_setup_queries(frm);
		_add_apply_button(frm);
		_add_capitalize_button(frm);
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
	test_parameter(frm, cdt, cdn) {
		_apply_parameter_mapping(frm, cdt, cdn);
	},
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

	frm.set_query("test_parameter", "reagent_lines", () => ({
		query: "nbs_customization.utils.placement.spec_lines.get_spec_test_parameters",
		filters: { analyzer_item: frm.doc.analyzer_pid },
	}));

	frm.set_query("item_code", "reagent_lines", (doc, cdt, cdn) => {
		const row = locals[cdt] && locals[cdt][cdn];
		const filters = { analyzer_item: frm.doc.analyzer_pid, reagent_role: "Test Reagent" };
		if (row && row.test_parameter) {
			filters.test_parameter = row.test_parameter;
		}
		return {
			query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
			filters: filters,
		};
	});

	frm.set_query("item_code", "consumable_lines", () => ({
		query: "nbs_customization.utils.placement.spec_lines.get_spec_consumables",
		filters: { analyzer_item: frm.doc.analyzer_pid },
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
				"Analyzer changed. Please verify that existing costing lines are still valid."
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
	if (frm.doc.docstatus !== 1 || frm.doc.linked_contract) return;

	frm.add_custom_button(
		__("Instrument Placement Contract"),
		() => {
			const d = new frappe.ui.Dialog({
				title: __("Apply Worksheet to Contract"),
				fields: [
					{
						fieldname: "asset",
						label: __("Asset"),
						fieldtype: "Link",
						options: "Asset",
						description: __(
							"Optional — leave blank to capitalize from stock on the Contract later."
						),
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
					frappe.model.open_mapped_doc({
						method: "nbs_customization.nbs_customization.doctype.instrument_pricing_worksheet.instrument_pricing_worksheet.make_instrument_placement_contract",
						frm: frm,
						args: {
							// Blank asset = capitalize later on the Contract.
							asset: asset || "",
							customer_site: customer_site,
						},
					});
				},
			});
			d.show();
		},
		__("Create")
	);
	frm.page.set_inner_btn_group_as_primary(__("Create"));
}

function _add_capitalize_button(frm) {
	if (frm.doc.docstatus === 2 || frm.doc.linked_contract) return;
	if (!frm.doc.analyzer_pid) return;

	frm.add_custom_button(
		__("Capitalize Analyzer"),
		() => {
			const d = new frappe.ui.Dialog({
				title: __("Capitalize Analyzer from Stock"),
				fields: [
					{
						label: __("Warehouse"),
						fieldname: "warehouse",
						fieldtype: "Link",
						options: "Warehouse",
						reqd: 1,
					},
					{
						label: __("Serial No"),
						fieldname: "serial_no",
						fieldtype: "Link",
						options: "Serial No",
						reqd: 1,
						get_query() {
							return {
								filters: {
									item_code: frm.doc.analyzer_pid,
									status: "Active",
								},
							};
						},
					},
				],
				primary_action_label: __("Create Asset"),
				primary_action(values) {
					d.hide();
					frm.call({
						method: "capitalize_analyzer",
						// doc: required — routes via run_doc_method; without it the
						// client prefixes the module path and get_attr fails (see 4776504).
						doc: frm.doc,
						args: {
							warehouse: values.warehouse,
							serial_no: values.serial_no,
						},
						freeze: true,
						freeze_message: __("Creating Asset..."),
						callback(r) {
							if (r.message) {
								frappe.msgprint(
									__("Asset {0} created. Pick it when creating the contract.", [
										r.message,
									])
								);
							}
						},
					});
				},
			});
			d.show();
		},
		__("Create")
	);
}

function _apply_parameter_mapping(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.test_parameter) return;

	if (_check_duplicate_test_parameter(frm, cdt, cdn)) return;

	if (!frm.doc.analyzer_pid) return;

	const requested_param = row.test_parameter;
	const requested_analyzer = frm.doc.analyzer_pid;

	frappe.call({
		method: "nbs_customization.utils.placement.spec_lines.get_spec_test_method_details",
		args: {
			analyzer_item: frm.doc.analyzer_pid,
			test_parameter: row.test_parameter,
		},
		callback(r) {
			const cur = locals[cdt] && locals[cdt][cdn];
			if (!cur || cur.test_parameter !== requested_param) return;
			if (frm.doc.analyzer_pid !== requested_analyzer) return;
			if (!r.message || !r.message.required_reagent) {
				frappe.msgprint({
					title: __("Unknown Parameter"),
					message: __(
						"Test Parameter {0} is not on this analyzer's specification. Reagent cleared.",
						[row.test_parameter]
					),
					indicator: "orange",
				});
				_clear_reagent_pack_fields(cdt, cdn);
				return;
			}
			if (row.item_code && row.item_code !== r.message.required_reagent) {
				frappe.show_alert({
					message: __("Reagent updated to {0} for this test.", [
						r.message.required_reagent,
					]),
					indicator: "orange",
				});
			}
			frappe.model.set_value(cdt, cdn, "item_code", r.message.required_reagent);
			frappe.model.set_value(cdt, cdn, "description", r.message.description || "");
		},
	});
}

function _check_duplicate_test_parameter(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const lines = frm.doc.reagent_lines || [];
	const duplicate = lines.find(
		(r) => r.test_parameter === row.test_parameter && r.name !== row.name
	);

	if (duplicate) {
		frappe.msgprint({
			title: __("Duplicate Parameter"),
			message: __("Test Parameter {0} is already in the list.", [row.test_parameter]),
			indicator: "orange",
		});
		frappe.model.set_value(cdt, cdn, "test_parameter", null);
		return true;
	}
	return false;
}

function _clear_reagent_pack_fields(cdt, cdn) {
	frappe.model.set_value(cdt, cdn, "item_code", null);
	frappe.model.set_value(cdt, cdn, "description", null);
	frappe.model.set_value(cdt, cdn, "pack_volume_ml", 0);
	frappe.model.set_value(cdt, cdn, "tests_per_pack", 0);
	frappe.model.set_value(cdt, cdn, "cogs_per_pack", 0);
}

function _fetch_reagent_details(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;

	if (row.test_parameter && frm.doc.analyzer_pid) {
		const requested_param = row.test_parameter;
		const requested_item = row.item_code;
		const requested_analyzer = frm.doc.analyzer_pid;
		frappe.call({
			method: "nbs_customization.utils.placement.spec_lines.get_spec_test_method_details",
			args: {
				analyzer_item: frm.doc.analyzer_pid,
				test_parameter: row.test_parameter,
			},
			callback(r) {
				const cur = locals[cdt] && locals[cdt][cdn];
				if (
					!cur ||
					cur.test_parameter !== requested_param ||
					cur.item_code !== requested_item
				)
					return;
				if (frm.doc.analyzer_pid !== requested_analyzer) return;
				if (r.message && r.message.required_reagent) {
					frappe.model.set_value(
						cdt,
						cdn,
						"pack_volume_ml",
						r.message.default_pack_volume_ml
					);
					frappe.model.set_value(
						cdt,
						cdn,
						"tests_per_pack",
						r.message.default_tests_per_pack
					);
					frappe.model.set_value(
						cdt,
						cdn,
						"cogs_per_pack",
						r.message.default_cogs_per_pack
					);
				} else {
					_fetch_reagent_defaults(cdt, cdn, row.item_code);
				}
			},
		});
		return;
	}
	_fetch_reagent_defaults(cdt, cdn, row.item_code);
}

function _fetch_reagent_defaults(cdt, cdn, item_code) {
	frappe.call({
		method: "frappe.client.get_value",
		args: {
			doctype: "Reagent Specification",
			filters: { item: item_code },
			fieldname: [
				"default_pack_volume_ml",
				"default_tests_per_pack",
				"default_cogs_per_pack",
			],
		},
		callback(r) {
			const cur = locals[cdt] && locals[cdt][cdn];
			if (!cur || cur.item_code !== item_code) return;
			if (!r.message) {
				// No spec row: clear so the previous item's pack values never linger.
				frappe.model.set_value(cdt, cdn, "pack_volume_ml", 0);
				frappe.model.set_value(cdt, cdn, "tests_per_pack", 0);
				frappe.model.set_value(cdt, cdn, "cogs_per_pack", 0);
				return;
			}
			const spec = r.message;
			frappe.model.set_value(cdt, cdn, "pack_volume_ml", spec.default_pack_volume_ml || 0);
			frappe.model.set_value(cdt, cdn, "tests_per_pack", spec.default_tests_per_pack || 0);
			frappe.model.set_value(cdt, cdn, "cogs_per_pack", spec.default_cogs_per_pack || 0);
		},
	});
}

function _fetch_consumable_details(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;

	if (frm.doc.analyzer_pid) {
		const requested_item = row.item_code;
		const requested_analyzer = frm.doc.analyzer_pid;
		frappe.call({
			method: "nbs_customization.utils.placement.spec_lines.get_spec_consumable_details",
			args: {
				analyzer_item: frm.doc.analyzer_pid,
				consumable_item: row.item_code,
			},
			callback(r) {
				const cur = locals[cdt] && locals[cdt][cdn];
				if (!cur || cur.item_code !== requested_item) return;
				if (frm.doc.analyzer_pid !== requested_analyzer) return;
				if (r.message && Object.keys(r.message).length) {
					// Always overwrite so replacing the item never keeps the old item's values.
					frappe.model.set_value(
						cdt,
						cdn,
						"consumption_qty",
						r.message.consumption_qty || 0
					);
					frappe.model.set_value(
						cdt,
						cdn,
						"consumption_frequency",
						r.message.consumption_frequency || null
					);
					frappe.model.set_value(
						cdt,
						cdn,
						"services_per_year",
						r.message.services_per_year || 0
					);
					frappe.model.set_value(
						cdt,
						cdn,
						"cogs_per_unit",
						r.message.default_cogs_per_unit || 0
					);
				} else {
					_fetch_consumable_defaults(cdt, cdn, requested_item);
				}
			},
		});
		return;
	}
	_fetch_consumable_defaults(cdt, cdn, row.item_code);
}

function _fetch_consumable_defaults(cdt, cdn, item_code) {
	frappe.call({
		method: "frappe.client.get_value",
		args: {
			doctype: "Reagent Specification",
			filters: { item: item_code },
			fieldname: [
				"default_consumption_qty",
				"default_consumption_frequency",
				"default_cogs_per_unit",
			],
		},
		callback(r) {
			const cur = locals[cdt] && locals[cdt][cdn];
			if (!cur || cur.item_code !== item_code) return;
			if (!r.message) {
				// No spec row: clear so the previous item's values never linger.
				frappe.model.set_value(cdt, cdn, "consumption_qty", 0);
				frappe.model.set_value(cdt, cdn, "consumption_frequency", null);
				frappe.model.set_value(cdt, cdn, "services_per_year", 0);
				frappe.model.set_value(cdt, cdn, "cogs_per_unit", 0);
				return;
			}
			const spec = r.message;
			frappe.model.set_value(cdt, cdn, "consumption_qty", spec.default_consumption_qty || 0);
			frappe.model.set_value(
				cdt,
				cdn,
				"consumption_frequency",
				spec.default_consumption_frequency || null
			);
			frappe.model.set_value(cdt, cdn, "services_per_year", 0);
			frappe.model.set_value(cdt, cdn, "cogs_per_unit", spec.default_cogs_per_unit || 0);
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
		method: "nbs_customization.utils.placement.spec_lines.get_analyzer_landed_cost",
		args: { analyzer_item: frm.doc.analyzer_pid },
		callback(r) {
			if (r.message && r.message.rate > 0) {
				frm.set_value("analyzer_landed_cost", r.message.rate);
			}
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
