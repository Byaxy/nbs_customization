frappe.ui.form.on("Instrument Placement Contract", {
	refresh(frm) {
		_setup_queries(frm);
		_add_capitalize_button(frm);
		_add_deployment_button(frm);
		_add_retrieve_button(frm);
		_add_refresh_recovery_button(frm);
		_show_recovery_progress(frm);
		_show_dashboard_alert(frm);
		_set_default_contract_title(frm);
	},

	customer(frm) {
		_set_default_contract_title(frm);
	},

	customer_name(frm) {
		_set_default_contract_title(frm);
	},

	contract_type(frm) {
		_set_default_contract_title(frm);
	},

	pricing_worksheet(frm) {
		_on_pricing_worksheet_change(frm);
	},

	asset(frm) {
		_fetch_serial_no(frm);
	},

	start_date(frm) {
		_compute_duration(frm);
	},

	end_date(frm) {
		_compute_duration(frm);
	},
});

frappe.ui.form.on("Contract Test Reagent Line", {
	item_code(frm, cdt, cdn) {
		_fetch_line_details(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Contract Consumable Line", {
	item_code(frm, cdt, cdn) {
		_fetch_consumable_line_details(frm, cdt, cdn);
	},
});

function _setup_queries(frm) {
	frm.set_query("customer_site", () => ({
		query: "frappe.contacts.doctype.address.address.address_query",
		filters: {
			link_doctype: "Customer",
			link_name: frm.doc.customer,
		},
	}));

	frm.set_query("asset", () => {
		const filters = {
			custom_current_deployment_status: "Warehouse",
			custom_current_placement_contract: ["is", "not set"],
		};
		if (frm.doc.asset) {
			filters.name = ["in", [frm.doc.asset]];
		}
		return { filters };
	});

	frm.set_query("item_code", "contract_reagent_lines", () => ({
		query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
		filters: { analyzer_item: frm.doc.analyzer_pid, reagent_role: "Test Reagent" },
	}));

	frm.set_query("item_code", "contract_consumable_lines", () => ({
		query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
		filters: { analyzer_item: frm.doc.analyzer_pid, reagent_role: "Non-Test Consumable" },
	}));

	frm.set_query("pricing_worksheet", () => {
		if (!frm.doc.customer) return { filters: { status: "Approved", linked_contract: ["is", "not set"] } };
		return {
			filters: {
				customer: frm.doc.customer,
				status: "Approved",
				linked_contract: ["is", "not set"],
			},
		};
	});
}

function _fetch_serial_no(frm) {
	if (!frm.doc.asset) return;
	frappe.db.get_value("Asset", frm.doc.asset, "custom_serial_no", (r) => {
		if (r && r.custom_serial_no) {
			frm.set_value("serial_no", r.custom_serial_no);
		}
	});
}

function _compute_duration(frm) {
	if (frm.doc.start_date && frm.doc.end_date) {
		const start = frappe.datetime.str_to_obj(frm.doc.start_date);
		const end = frappe.datetime.str_to_obj(frm.doc.end_date);
		const months = (end.getFullYear() - start.getFullYear()) * 12
			+ (end.getMonth() - start.getMonth());
		frm.set_value("contract_duration_months", Math.max(months, 0));
	}
}

function _on_pricing_worksheet_change(frm) {
	if (!frm.doc.pricing_worksheet || !frm.doc.__islocal) return;

	frappe.call({
		method: "frappe.client.get",
		args: { doctype: "Instrument Pricing Worksheet", name: frm.doc.pricing_worksheet },
		callback(r) {
			if (!r.message) return;
			const ws = r.message;

			frm.set_value("contract_type", ws.contract_type);
			frm.set_value("analyzer_pid", ws.analyzer_pid);
			frm.set_value("total_recovery_target", ws.final_revenue_target);
			frm.set_value("min_monthly_value", ws.min_monthly_value || 0);
			frm.set_value("breach_threshold", 3);
			frm.set_value("grace_period_days", 30);
			frm.set_value("revenue_share_pct", ws.contract_type === "CPT" ? (ws.required_revenue_share_pct || 0) : 0);

			const start = frappe.datetime.now_date();
			const end = frappe.datetime.add_days(start, (ws.contract_years || 1) * 365);
			frm.set_value("start_date", start);
			frm.set_value("end_date", end);

			frm.clear_table("contract_reagent_lines");
			frm.clear_table("contract_consumable_lines");

			(ws.reagent_lines || []).forEach((line) => {
				const child = frm.add_child("contract_reagent_lines");
				child.item_code = line.item_code;
				child.test_parameter = line.test_parameter;
				child.standard_price = line.cogs_per_pack;
				child.monthly_test_volume = line.monthly_test_volume;
				child.contract_price = line.selling_price_per_pack || 0;
				child.qty_required_total = line.packs_needed || 0;
				child.min_monthly_qty = Math.ceil((line.monthly_test_volume || 0) / (line.tests_per_pack || 1));
				child.cogs_per_unit = line.cogs_per_pack;
				child.agreed_test_price = line.price_per_test || 0;
			});

			(ws.consumable_lines || []).forEach((line) => {
				const child = frm.add_child("contract_consumable_lines");
				child.item_code = line.item_code;
				child.standard_price = line.cogs_per_unit;
				child.contract_price = 0;
				child.qty_required_total = line.total_units_over_term || 0;
				child.cogs_per_unit = line.cogs_per_unit;
			});

			frm.refresh_field("contract_reagent_lines");
			frm.refresh_field("contract_consumable_lines");
			_set_default_contract_title(frm);
		},
	});
}

function _set_default_contract_title(frm) {
	if (frm.doc.contract_title && !frm.doc.__islocal) return;
	if (!frm.doc.customer_name || !frm.doc.contract_type) return;
	frm.set_value("contract_title",
		`${frm.doc.customer_name} - ${frm.doc.contract_type} Placement Contract`);
}

function _fetch_line_details(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;

	frappe.call({
		method: "frappe.client.get_value",
		args: {
			doctype: "Reagent Specification",
			filters: { item: row.item_code },
			fieldname: ["default_cogs_per_pack"],
		},
		callback(r) {
			if (!r.message) return;
			frappe.model.set_value(cdt, cdn, "cogs_per_unit", r.message.default_cogs_per_pack);
		},
	});
}

function _fetch_consumable_line_details(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;

	frappe.call({
		method: "frappe.client.get_value",
		args: {
			doctype: "Reagent Specification",
			filters: { item: row.item_code },
			fieldname: ["default_cogs_per_unit"],
		},
		callback(r) {
			if (!r.message) return;
			frappe.model.set_value(cdt, cdn, "cogs_per_unit", r.message.default_cogs_per_unit);
		},
	});
}

function _add_capitalize_button(frm) {
	if (frm.doc.__islocal) return;
	if (frm.doc.docstatus !== 0) return;
	if (frm.doc.asset) return;
	if (!frm.doc.analyzer_pid) return;

	frm.add_custom_button(__("Capitalize for Placement"), () => {
		const d = new frappe.ui.Dialog({
			title: __("Capitalize Analyzer from Stock"),
			fields: [
				{
					label: __("Warehouse"),
					fieldname: "warehouse",
					fieldtype: "Link",
					options: "Warehouse",
					reqd: 1,
					get_query() {
						return {
							filters: {
								company: frappe.defaults.get_default("company"),
							},
						};
					},
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
								status: "In Store",
								warehouse: d.get_value("warehouse") || "",
							},
						};
					},
				},
			],
			primary_action_label: __("Create Asset"),
			primary_action(values) {
				d.hide();
				frappe.dom.freeze(__("Creating Asset..."));
				frm.call({
					method: "create_asset_from_stock",
					args: {
						warehouse: values.warehouse,
						serial_no: values.serial_no,
					},
					callback(r) {
						frappe.dom.unfreeze();
						if (!r.exc) {
							frappe.msgprint(__("Asset {0} created and capitalized.", [r.message]));
							frm.refresh();
						}
					},
				});
			},
		});
		d.show();
	}, __("Create"));
}

function _add_deployment_button(frm) {
	if (frm.doc.contract_status !== "Active") return;
	if (frm.doc.__islocal) return;

	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Analyzer Deployment",
			filters: { contract: frm.doc.name, docstatus: ["<", 2] },
			fields: ["name"],
			limit: 1,
		},
		callback(r) {
			if (r.message && r.message.length) {
				frm.add_custom_button(__("Analyzer Deployment"), () => {
					frappe.set_route("Form", "Analyzer Deployment", r.message[0].name);
				}, __("View"));
			} else {
				frm.add_custom_button(__("Analyzer Deployment"), () => {
					frappe.model.open_mapped_doc({
						method: "nbs_customization.controllers.placement.contract.make_deployment",
						frm: frm,
					});
				}, __("Create"));
			}
		},
	});
}

function _add_retrieve_button(frm) {
	if (frm.doc.contract_status !== "Active") return;

	frm.add_custom_button(__("Retrieve Analyzer"), () => {
		frappe.model.open_mapped_doc({
			method: "nbs_customization.controllers.placement.contract.make_repossession_request",
			frm: frm,
		});
	}, __("Actions"));
}

function _add_refresh_recovery_button(frm) {
	if (frm.doc.docstatus !== 1) return;

	frm.add_custom_button(__("Refresh Recovery"), () => {
		frm.call("recompute_recovery").then(() => {
			frm.refresh();
		});
	}, __("Actions"));
}

function _progress_color(pct) {
	if (pct <= 0) return "#6c757d";
	if (pct < 50) return "#dc3545";
	if (pct < 75) return "#fd7e14";
	if (pct < 100) return "#ffc107";
	return "#28a745";
}

function _show_recovery_progress(frm) {
	const target = frm.doc.total_recovery_target;
	if (!target) return;

	frm.dashboard.progress_area.body.empty();

	const collected = frm.doc.recovery_pct_collected || 0;
	const invoiced = frm.doc.recovery_pct_invoiced || 0;

	frm.dashboard.progress_area.body.append(`
		<div class="row" style="margin: 0 -5px;">
			<div class="col-sm-6" style="padding: 0 5px;">
				<div class="progress-chart">
					<h6 style="margin: 5px 0 2px; font-weight: 600; font-size: 12px;">${__("Invoiced")}</h6>
					<div class="progress" style="height: 18px;">
						<div class="progress-bar" style="width: ${Math.max(invoiced, 3)}%; background-color: ${_progress_color(invoiced)};">
							${invoiced > 8 ? `${Math.round(invoiced)}%` : ""}
						</div>
					</div>
					<p style="margin: 2px 0 0; font-size: 11px; color: #888;">${Math.round(invoiced)}% ${__("of target recovered")}</p>
				</div>
			</div>
			<div class="col-sm-6" style="padding: 0 5px;">
				<div class="progress-chart">
					<h6 style="margin: 5px 0 2px; font-weight: 600; font-size: 12px;">${__("Collected / Paid")}</h6>
					<div class="progress" style="height: 18px;">
						<div class="progress-bar" style="width: ${Math.max(collected, 3)}%; background-color: ${_progress_color(collected)};">
							${collected > 8 ? `${Math.round(collected)}%` : ""}
						</div>
					</div>
					<p style="margin: 2px 0 0; font-size: 11px; color: #888;">${Math.round(collected)}% ${__("of target collected")}</p>
				</div>
			</div>
		</div>
	`);

	frm.dashboard.progress_area.show();
	frm.dashboard.show();
}

function _show_dashboard_alert(frm) {
	if (!frm.doc.custom_instrument_placement_contract) return;

	const contract_link = frappe.utils.get_form_link(
		"Instrument Placement Contract",
		frm.doc.custom_instrument_placement_contract,
		true
	);
	frm.dashboard.add_comment(
		__("Linked to Placement Contract: {0} — {1}",
			[contract_link, frm.doc.custom_instrument_placement_contract])
	);
}
