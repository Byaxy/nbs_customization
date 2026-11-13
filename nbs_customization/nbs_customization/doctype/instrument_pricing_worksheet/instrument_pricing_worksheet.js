frappe.ui.form.on("Instrument Pricing Worksheet", {
	refresh(frm) {
		_setup_queries(frm);
		_add_apply_button(frm);
		_add_capitalize_button(frm);
		_add_panel_button(frm);
		_add_cost_basis_button(frm);
		frm.trigger("update_indicators");
		_customize_submit_message(frm);
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},

	update_indicators(frm) {
		const STATUSES = {
			Draft: "orange",
			Approved: "green",
			"Applied to Contract": "purple",
			Cancelled: "red",
		};
		frm.page.set_indicator(__(frm.doc.status), STATUSES[frm.doc.status] || "gray");
	},

	analyzer_pid(frm) {
		_fetch_analyzer_type(frm);
		_refresh_reagent_queries(frm);
		_fetch_analyzer_landed_cost(frm);
		_fetch_analyzer_selling_price(frm);
		_add_panel_button(frm);
		_add_cost_basis_button(frm);
	},

	contract_type(frm) {
		_auto_set_calculation_output(frm);
	},

	posting_date(frm) {
		_fetch_analyzer_selling_price(frm);
	},
});

frappe.ui.form.on("Worksheet Test Reagent Line", {
	test_parameter(frm, cdt, cdn) {
		_apply_parameter_mapping(frm, cdt, cdn);
	},
	item_code(frm, cdt, cdn) {
		_fetch_reagent_details(frm, cdt, cdn);
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
			custom_analyzer_profile: ["!=", ""],
		},
	}));
	_refresh_reagent_queries(frm);
}

function _refresh_reagent_queries(frm) {
	if (!frm.doc.analyzer_pid) return;
	frm.set_query("test_parameter", "reagent_lines", () => ({
		query: "nbs_customization.utils.placement.spec_lines.get_analyzer_test_parameters",
		filters: { analyzer_item: frm.doc.analyzer_pid },
	}));
	frm.set_query("item_code", "reagent_lines", (doc, cdt, cdn) => {
		const row = locals[cdt] && locals[cdt][cdn];
		const filters = { analyzer_item: frm.doc.analyzer_pid };
		if (row && row.test_parameter) {
			filters.test_parameter = row.test_parameter;
		}
		return {
			query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
			filters: filters,
		};
	});
	frm.set_query("item_code", "consumable_lines", () => ({
		query: "nbs_customization.utils.placement.spec_lines.get_analyzer_consumables",
		filters: { analyzer_item: frm.doc.analyzer_pid },
	}));
}

function _fetch_analyzer_type(frm) {
	if (!frm.doc.analyzer_pid) return;
	frappe.db
		.get_value("Analyzer Profile", { analyzer_item: frm.doc.analyzer_pid }, "analyzer_type")
		.then((r) => {
			if (r.message && r.message.analyzer_type) {
				frm.set_value("analyzer_type", r.message.analyzer_type);
			}
		});
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
							"Optional — leave blank to capitalize from stock on the Contract."
						),
						get_query() {
							return {
								filters: {
									docstatus: 1,
									custom_current_deployment_status: "Warehouse",
									custom_current_placement_contract: ["is", "not set"],
									status: ["not in", ["Sold", "Scrapped"]],
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
						args: { asset: asset || "", customer_site },
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
								filters: { item_code: frm.doc.analyzer_pid, status: "Active" },
							};
						},
					},
				],
				primary_action_label: __("Create Asset"),
				primary_action(values) {
					d.hide();
					frm.call({
						method: "capitalize_analyzer",
						doc: frm.doc,
						args: values,
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

function _add_cost_basis_button(frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.analyzer_pid || !frm.doc.term_months) return;
	frm.add_custom_button(
		__("Load Cost Basis"),
		() => {
			frappe.confirm(
				__(
					"Add consumables, calibration, control and maintenance costs that are not already on the worksheet?"
				),
				() => _load_cost_basis(frm)
			);
		},
		__("Tools")
	);
}

function _load_cost_basis(frm) {
	frappe.call({
		method: "nbs_customization.utils.placement.spec_lines.get_analyzer_cost_basis",
		args: {
			analyzer_item: frm.doc.analyzer_pid,
			term_months: frm.doc.term_months,
			operational_days_per_month: frm.doc.operational_days_per_month || 0,
			monthly_test_volume: frm.doc.total_monthly_tests || 0,
			posting_date: frm.doc.posting_date,
		},
		freeze: true,
		callback(r) {
			const rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint({
					title: __("No Cost Basis"),
					message: __(
						"This analyzer has no consumables, calibration, control or maintenance rows."
					),
					indicator: "orange",
				});
				return;
			}
			let added = 0;
			let updated = 0;
			const counts = {};
			rows.forEach((row) => {
				counts[row.source_type] = (counts[row.source_type] || 0) + 1;
				const existing = _find_cost_basis_line(frm, row);
				if (existing) {
					frappe.model.set_value(
						existing.doctype,
						existing.name,
						"quantity_over_term",
						row.quantity_over_term
					);
					frappe.model.set_value(
						existing.doctype,
						existing.name,
						"cogs_per_unit",
						row.cogs_per_unit || 0
					);
					frappe.model.set_value(
						existing.doctype,
						existing.name,
						"standard_selling_price_per_unit",
						row.standard_selling_price_per_unit || 0
					);
					updated += 1;
					return;
				}
				const child = frappe.model.add_child(
					frm.doc,
					"Worksheet Consumable Line",
					"consumable_lines"
				);
				child.source_type = row.source_type;
				child.source_reference = row.source_reference || "";
				child.is_auto = 1;
				child.item_code = row.item_code;
				child.description = row.description || "";
				child.quantity_over_term = row.quantity_over_term;
				child.consumption_frequency = "Computed Over Term";
				child.cogs_per_unit = row.cogs_per_unit || 0;
				child.standard_selling_price_per_unit = row.standard_selling_price_per_unit || 0;
				added += 1;
			});
			frm.refresh_field("consumable_lines");
			frappe.show_alert({
				message: __("Added {0}, updated {1} cost-basis rows. {2}", [
					added,
					updated,
					Object.entries(counts)
						.map(([type, count]) => `${type}: ${count}`)
						.join(", "),
				]),
				indicator: "green",
			});
		},
	});
}

function _find_cost_basis_line(frm, row) {
	return (frm.doc.consumable_lines || []).find(
		(line) =>
			line.item_code === row.item_code &&
			(line.source_type || "Analyzer Consumable") === row.source_type &&
			(line.source_reference || "") === (row.source_reference || "")
	);
}

function _add_panel_button(frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.analyzer_pid) return;
	frm.add_custom_button(
		__("Load Panel"),
		() => {
			const d = new frappe.ui.Dialog({
				title: __("Load Panel"),
				fields: [
					{
						fieldname: "panel",
						label: __("Test Panel"),
						fieldtype: "Link",
						options: "Test Panel",
						reqd: 1,
						get_query() {
							return { filters: { is_active: 1 } };
						},
					},
					{
						fieldname: "monthly_volume",
						label: __("Monthly Tests per Test"),
						fieldtype: "Float",
						default: 0,
					},
					{
						fieldname: "replace",
						label: __("Replace existing reagent lines"),
						fieldtype: "Check",
					},
				],
				primary_action_label: __("Add rows"),
				primary_action({ panel, monthly_volume, replace }) {
					d.hide();
					_expand_panel(frm, panel, replace, monthly_volume || 0);
				},
			});
			d.show();
		},
		__("Tools")
	);
}

function _expand_panel(frm, panel, replace, monthly_volume) {
	frappe.call({
		method: "nbs_customization.utils.placement.spec_lines.expand_panel",
		args: {
			analyzer_item: frm.doc.analyzer_pid,
			panel: panel,
			posting_date: frm.doc.posting_date,
		},
		freeze: true,
		callback(r) {
			const rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint({
					title: __("No Reagents"),
					message: __(
						"Panel {0} has no tests with reagent components on this analyzer.",
						[panel]
					),
					indicator: "orange",
				});
				return;
			}
			if (replace) frm.clear_table("reagent_lines");
			_drop_empty_reagent_rows(frm);
			let added = 0;
			rows.forEach((component) => {
				const existing = (frm.doc.reagent_lines || []).find(
					(row) =>
						row.test_parameter === component.test_parameter &&
						row.item_code === component.reagent_item
				);
				if (existing) {
					if (monthly_volume) {
						frappe.model.set_value(
							existing.doctype,
							existing.name,
							"monthly_test_volume",
							monthly_volume
						);
					}
					return;
				}
				const child = frappe.model.add_child(
					frm.doc,
					"Worksheet Test Reagent Line",
					"reagent_lines"
				);
				_apply_component(child, component, component.test_parameter, monthly_volume);
				added += 1;
			});
			frm.refresh_field("reagent_lines");
			frappe.show_alert({
				message: __("Added {0} reagent rows from {1}.", [added, panel]),
				indicator: "green",
			});
		},
	});
}

function _apply_parameter_mapping(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.test_parameter || !frm.doc.analyzer_pid) return;
	const requested_param = row.test_parameter;
	const requested_analyzer = frm.doc.analyzer_pid;
	const monthly_volume = row.monthly_test_volume || 0;
	frappe.call({
		method: "nbs_customization.utils.placement.spec_lines.get_test_reagent_components",
		args: {
			analyzer_item: frm.doc.analyzer_pid,
			test_parameter: requested_param,
			posting_date: frm.doc.posting_date,
		},
		callback(r) {
			const cur = locals[cdt] && locals[cdt][cdn];
			if (!cur || cur.test_parameter !== requested_param) return;
			if (frm.doc.analyzer_pid !== requested_analyzer) return;
			const components = r.message || [];
			if (!components.length) {
				frappe.msgprint({
					title: __("Unknown Parameter"),
					message: __("Test {0} has no reagents on this analyzer.", [requested_param]),
					indicator: "orange",
				});
				_clear_reagent_pack_fields(cdt, cdn);
				return;
			}
			_apply_component(cur, components[0], requested_param, monthly_volume);
			components.slice(1).forEach((component) => {
				if (_line_exists(frm, requested_param, component.reagent_item)) return;
				const child = frappe.model.add_child(
					frm.doc,
					"Worksheet Test Reagent Line",
					"reagent_lines"
				);
				_apply_component(child, component, requested_param, monthly_volume);
			});
			frm.refresh_field("reagent_lines");
			if (components.length > 1) {
				frappe.show_alert({
					message: __("Added {0} reagent rows for {1}.", [
						components.length,
						requested_param,
					]),
					indicator: "green",
				});
			}
		},
	});
}

function _apply_component(row, component, test_parameter, monthly_volume) {
	row.test_parameter = test_parameter;
	row.item_code = component.reagent_item;
	row.description = component.description || "";
	row.component_role = component.component_role || "";
	row.pack_volume_ml = component.default_pack_volume_ml || 0;
	row.tests_per_pack = component.default_tests_per_pack || 0;
	row.gross_tests_per_pack = component.default_tests_per_pack || 0;
	row.cogs_per_pack = component.default_cogs_per_pack || 0;
	row.standard_selling_price_per_pack = component.standard_selling_price_per_pack || 0;
	if (monthly_volume !== undefined) row.monthly_test_volume = monthly_volume;
}

function _drop_empty_reagent_rows(frm) {
	const rows = frm.doc.reagent_lines || [];
	for (let i = rows.length - 1; i >= 0; i--) {
		if (!rows[i].item_code && !rows[i].test_parameter) frm.doc.reagent_lines.splice(i, 1);
	}
}

function _line_exists(frm, test_parameter, item_code) {
	return (frm.doc.reagent_lines || []).some(
		(row) => row.test_parameter === test_parameter && row.item_code === item_code
	);
}

function _clear_reagent_pack_fields(cdt, cdn) {
	for (const field of ["item_code", "description", "component_role"]) {
		frappe.model.set_value(cdt, cdn, field, null);
	}
	for (const field of [
		"pack_volume_ml",
		"tests_per_pack",
		"gross_tests_per_pack",
		"cogs_per_pack",
		"standard_selling_price_per_pack",
	]) {
		frappe.model.set_value(cdt, cdn, field, 0);
	}
}

function _fetch_reagent_details(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;
	if (row.test_parameter && frm.doc.analyzer_pid) {
		const requested_param = row.test_parameter;
		const requested_item = row.item_code;
		const requested_analyzer = frm.doc.analyzer_pid;
		frappe.call({
			method: "nbs_customization.utils.placement.spec_lines.get_test_reagent_components",
			args: {
				analyzer_item: frm.doc.analyzer_pid,
				test_parameter: requested_param,
				posting_date: frm.doc.posting_date,
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
				const component = (r.message || []).find(
					(value) => value.reagent_item === requested_item
				);
				if (component) {
					_apply_component(cur, component, requested_param);
					frm.refresh_field("reagent_lines");
				} else {
					_fetch_reagent_defaults(cdt, cdn, requested_item);
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
			const spec = r.message || {};
			frappe.model.set_value(cdt, cdn, "pack_volume_ml", spec.default_pack_volume_ml || 0);
			frappe.model.set_value(cdt, cdn, "tests_per_pack", spec.default_tests_per_pack || 0);
			frappe.model.set_value(
				cdt,
				cdn,
				"gross_tests_per_pack",
				spec.default_tests_per_pack || 0
			);
			frappe.model.set_value(cdt, cdn, "cogs_per_pack", spec.default_cogs_per_pack || 0);
		},
	});
}

function _fetch_consumable_details(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;
	const requested_item = row.item_code;
	const requested_analyzer = frm.doc.analyzer_pid;
	frappe.call({
		method: "nbs_customization.utils.placement.spec_lines.get_analyzer_consumable_details",
		args: { analyzer_item: frm.doc.analyzer_pid, consumable_item: row.item_code },
		callback(r) {
			const cur = locals[cdt] && locals[cdt][cdn];
			if (
				!cur ||
				cur.item_code !== requested_item ||
				frm.doc.analyzer_pid !== requested_analyzer
			)
				return;
			const data = r.message || {};
			frappe.model.set_value(cdt, cdn, "consumption_qty", data.consumption_qty || 0);
			frappe.model.set_value(
				cdt,
				cdn,
				"consumption_frequency",
				data.consumption_frequency || null
			);
			frappe.model.set_value(cdt, cdn, "services_per_year", data.services_per_year || 0);
			frappe.model.set_value(cdt, cdn, "cogs_per_unit", data.default_cogs_per_unit || 0);
		},
	});
}

function _fetch_analyzer_selling_price(frm) {
	const analyzer = frm.doc.analyzer_pid;
	if (!analyzer) {
		frm.set_value("analyzer_standard_selling_price", 0);
		return;
	}
	frappe.call({
		method: "nbs_customization.utils.placement.spec_lines.get_analyzer_standard_selling_price",
		args: { analyzer_item: analyzer, posting_date: frm.doc.posting_date },
		callback(r) {
			if (frm.doc.analyzer_pid !== analyzer) return;
			const rate = (r.message && r.message.rate) || 0;
			frm.set_value("analyzer_standard_selling_price", rate);
			if (rate <= 0) {
				frappe.show_alert({
					message: __("No active Standard Selling price for {0}.", [analyzer]),
					indicator: "orange",
				});
			}
		},
	});
}

function _fetch_analyzer_landed_cost(frm) {
	if (!frm.doc.analyzer_pid) return;
	frappe.call({
		method: "nbs_customization.utils.placement.spec_lines.get_analyzer_landed_cost",
		args: { analyzer_item: frm.doc.analyzer_pid },
		callback(r) {
			if (r.message && r.message.rate > 0)
				frm.set_value("analyzer_landed_cost", r.message.rate);
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
