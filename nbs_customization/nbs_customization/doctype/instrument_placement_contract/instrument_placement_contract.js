frappe.ui.form.on("Instrument Placement Contract", {
	refresh(frm) {
		_setup_queries(frm);
		_compute_duration(frm);
		_add_capitalize_button(frm);
		_add_deployment_button(frm);
		_add_retrieve_button(frm);
		_add_refresh_recovery_button(frm);
		_add_historical_link_button(frm);
		_show_dashboard_alert(frm);
		_set_default_contract_title(frm);
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
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

	contract_template(frm) {
		_fetch_contract_terms(frm);
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
	// Lines mirror the linked worksheet (read-only); no per-row fetching.
});

frappe.ui.form.on("Contract Consumable Line", {
	// Lines mirror the linked worksheet (read-only); no per-row fetching.
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
			docstatus: 1,
			custom_current_deployment_status: "Warehouse",
			custom_current_placement_contract: ["is", "not set"],
			status: ["not in", ["Sold", "Scrapped"]],
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
		if (!frm.doc.customer)
			return { filters: { status: "Approved", linked_contract: ["is", "not set"] } };
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
		let months =
			(end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth());
		if (end.getDate() > start.getDate()) months += 1;
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

			if (ws.company) {
				frm.set_value("company", ws.company);
			}
			frm.set_value("contract_type", ws.contract_type);
			frm.set_value("analyzer_pid", ws.analyzer_pid);
			frm.set_value("term_months", ws.term_months || 12);
			frm.set_value("total_recovery_target", ws.final_revenue_target);
			frm.set_value("avg_samples_per_day", ws.avg_samples_per_day || 0);
			frm.set_value("operational_days_per_month", ws.operational_days_per_month || 0);
			frm.set_value(
				"analyzer_standard_selling_price",
				ws.analyzer_standard_selling_price || 0
			);
			frm.set_value(
				"annual_service_maintenance_rate_pct",
				ws.annual_service_maintenance_rate_pct || 0
			);
			frm.set_value("total_maintenance_cost", ws.total_maintenance_cost || 0);
			frm.set_value("standard_sale_base", ws.standard_sale_base || 0);
			frm.set_value("total_test_reagent_value", ws.total_test_reagent_value || 0);
			frm.set_value("total_consumable_value", ws.total_consumable_value || 0);
			frm.set_value(
				"contract_gross_test_revenue",
				ws.total_gross_test_revenue_over_term || 0
			);
			frm.set_value("contract_charged_value", ws.contract_charged_value || 0);
			frm.set_value("net_revenue_target", ws.net_revenue_target || 0);
			frm.set_value("wht_rate_pct", ws.wht_rate_pct || 0);
			frm.set_value("wht_amount", ws.wht_amount || 0);
			frm.set_value("total_outright_sale_value", ws.total_outright_sale_value || 0);
			frm.set_value("outright_gap_amount", ws.outright_gap_amount || 0);
			frm.set_value("outright_gap_pct", ws.outright_gap_pct || 0);
			frm.set_value("benchmark_tolerance_pct", ws.benchmark_tolerance_pct || 5);
			frm.set_value("benchmark_status", ws.benchmark_status || "");
			frm.set_value(
				"product_only_standard_sale_base",
				ws.product_only_standard_sale_base || 0
			);
			frm.set_value("product_only_outright_value", ws.product_only_outright_value || 0);
			frm.set_value("product_only_contract_value", ws.product_only_contract_value || 0);
			frm.set_value("product_only_gap_pct", ws.product_only_gap_pct || 0);
			frm.set_value("min_monthly_value", ws.min_monthly_value || 0);
			frm.set_value("breach_threshold", 3);
			frm.set_value("grace_period_days", 30);
			frm.set_value(
				"revenue_share_pct",
				ws.contract_type === "CPT" ? ws.required_revenue_share_pct || 0 : 0
			);

			const start = frappe.datetime.now_date();
			const end = frappe.datetime.add_months(start, ws.term_months || 12);
			frm.set_value("start_date", start);
			frm.set_value("end_date", end);

			frm.clear_table("contract_reagent_lines");
			frm.clear_table("contract_consumable_lines");

			(ws.reagent_lines || []).forEach((line) => {
				const child = frm.add_child("contract_reagent_lines");
				child.item_code = line.item_code;
				child.test_parameter = line.test_parameter;
				child.pack_volume_ml = line.pack_volume_ml || 0;
				child.standard_price = line.cogs_per_pack;
				child.monthly_test_volume = line.monthly_test_volume;
				child.contract_price = line.selling_price_per_pack || 0;
				child.qty_required_total = line.packs_needed || 0;
				const tests_per_pack =
					line.reportable_tests_per_pack ||
					line.gross_tests_per_pack ||
					line.tests_per_pack;
				child.min_monthly_qty = tests_per_pack
					? Math.ceil((line.monthly_test_volume || 0) / tests_per_pack)
					: 0;
				child.cogs_per_unit = line.cogs_per_pack;
				child.agreed_test_price = line.price_per_test || 0;
				child.bg_consumption_ml_day = line.bg_consumption_ml_day || 0;
				child.bg_consumption_ml_month = line.bg_consumption_ml_month || 0;
				child.consumption_ml_per_test = line.consumption_ml_per_test || 0;
				child.total_consumption_ml_month = line.total_consumption_ml_month || 0;
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

function _fetch_contract_terms(frm) {
	if (!frm.doc.contract_template) return;
	const requested_template = frm.doc.contract_template;
	frappe.call({
		method: "erpnext.crm.doctype.contract_template.contract_template.get_contract_template",
		args: {
			template_name: frm.doc.contract_template,
			doc: frm.doc,
		},
		callback(r) {
			// Ignore stale responses after a rapid template switch.
			if (frm.doc.contract_template !== requested_template) return;
			if (r.message && r.message.contract_terms) {
				frm.set_value("contract_terms", r.message.contract_terms);
			}
		},
	});
}

function _set_default_contract_title(frm) {
	if (frm.doc.contract_title && !frm.doc.__islocal) return;
	if (!frm.doc.customer_name || !frm.doc.contract_type) return;
	frm.set_value(
		"contract_title",
		`${frm.doc.customer_name} - ${frm.doc.contract_type} Placement Contract`
	);
}

function _add_capitalize_button(frm) {
	if (frm.doc.__islocal) return;
	if (frm.doc.docstatus !== 0) return;
	if (frm.doc.asset) return;
	if (!frm.doc.analyzer_pid) return;

	frm.add_custom_button(
		__("Capitalize for Placement"),
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
									status: "Active",
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
						doc: frm.doc,
						args: {
							warehouse: values.warehouse,
							serial_no: values.serial_no,
						},
						callback(r) {
							frappe.dom.unfreeze();
							if (!r.exc) {
								frappe.msgprint(
									__("Asset {0} created and capitalized.", [r.message])
								);
								frm.refresh();
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
				frm.add_custom_button(
					__("Analyzer Deployment"),
					() => {
						frappe.set_route("Form", "Analyzer Deployment", r.message[0].name);
					},
					__("View")
				);
			} else {
				frm.add_custom_button(
					__("Analyzer Deployment"),
					() => {
						frappe.model.open_mapped_doc({
							method: "nbs_customization.controllers.placement.contract.make_deployment",
							frm: frm,
						});
					},
					__("Create")
				);
			}
		},
	});
}

function _add_retrieve_button(frm) {
	if (frm.doc.contract_status !== "Active") return;

	frm.add_custom_button(
		__("Retrieve Analyzer"),
		() => {
			frappe.model.open_mapped_doc({
				method: "nbs_customization.controllers.placement.contract.make_repossession_request",
				frm: frm,
			});
		},
		__("Actions")
	);
	frm.page.set_inner_btn_group_as_primary(__("Actions"));
}

function _add_refresh_recovery_button(frm) {
	if (frm.doc.docstatus !== 1) return;

	frm.add_custom_button(
		__("Refresh Recovery"),
		() => {
			frm.call("recompute_recovery").then(() => {
				frm.refresh();
			});
		},
		__("Actions")
	);
	frm.page.set_inner_btn_group_as_primary(__("Actions"));
}

function _add_historical_link_button(frm) {
	if (frm.doc.docstatus !== 1) return;
	if (!["Active", "Ownership Pending", "Fulfilled"].includes(frm.doc.contract_status)) return;

	frm.add_custom_button(
		__("Link Historical Transactions"),
		() => _open_historical_link_dialog(frm),
		__("Actions")
	);
	frm.page.set_inner_btn_group_as_primary(__("Actions"));
}

function _open_historical_link_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Link Historical Transactions"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "Data",
				fieldname: "search",
				label: __("Search Sales Order"),
			},
			{
				fieldtype: "HTML",
				fieldname: "results",
			},
		],
		primary_action_label: __("Link Selected"),
		primary_action() {
			_link_selected_historical(frm, d);
		},
		on_page_show() {
			_fetch_historical_sales_orders(frm, d);
		},
	});

	d.set_secondary_action_label(__("Refresh"));
	d.set_secondary_action(() => _fetch_historical_sales_orders(frm, d));
	d.fields_dict.search.$input.on(
		"input",
		frappe.utils.debounce(() => _fetch_historical_sales_orders(frm, d), 300)
	);
	d.fields_dict.search.$input.on("keydown", (e) => {
		if (e.key === "Enter") {
			e.preventDefault();
			_fetch_historical_sales_orders(frm, d);
		}
	});
	d.disable_primary_action();
	d.show();
}

function _fetch_historical_sales_orders(frm, d) {
	const search = d.fields_dict.search.get_value() || null;
	const request_id = (d._historical_request_id || 0) + 1;
	d._historical_request_id = request_id;

	d.disable_primary_action();
	d.fields_dict.results.$wrapper.html(
		`<p class="text-muted">${__("Loading Sales Orders...")}</p>`
	);
	frappe.call({
		method: "nbs_customization.utils.placement.historical_link.get_linkable_sales_orders",
		args: { contract: frm.doc.name, search: search },
		callback(r) {
			if (request_id !== d._historical_request_id) return;
			const rows = r.message || [];
			_render_historical_sales_orders(d, rows);
			if (rows.some((row) => !row.blocked)) {
				d.enable_primary_action();
			}
		},
	});
}

function _render_historical_sales_orders(d, rows) {
	const $results = d.fields_dict.results.$wrapper;
	if (!rows.length) {
		$results.html(
			`<p class="text-muted">${__("No eligible unlinked Sales Orders found.")}</p>`
		);
		return;
	}

	const escape = frappe.utils.escape_html;
	const header = `
		<div class="table-responsive">
			<table class="table table-bordered table-condensed">
				<thead>
					<tr>
						<th style="width: 32px;">
							<input type="checkbox" class="historical-select-all">
						</th>
						<th>${__("Sales Order")}</th>
						<th>${__("Date")}</th>
						<th class="text-right">${__("Amount")}</th>
						<th>${__("Items")}</th>
						<th>${__("Detected Type")}</th>
						<th>${__("Warnings")}</th>
					</tr>
				</thead>
				<tbody>
	`;

	const body = rows
		.map((row) => {
			const detected_type = row.suggested_type
				? escape(row.suggested_type)
				: `<span class="text-muted">${__("Not detected")}</span>`;
			const warnings = (row.warnings || [])
				.map((warning) => `<div class="text-danger small">${escape(warning)}</div>`)
				.join("");
			return `
				<tr>
					<td>
						<input type="checkbox" class="historical-row"
							data-name="${escape(row.name)}"
							${row.blocked ? "disabled" : ""}>
					</td>
					<td>
						<a href="/app/sales-order/${escape(row.name)}">${escape(row.name)}</a>
					</td>
					<td>${escape(row.date)}</td>
					<td class="text-right">${format_currency(row.grand_total)}</td>
					<td>${escape(row.item_summary)}</td>
					<td>${detected_type}</td>
					<td>${warnings}</td>
				</tr>
			`;
		})
		.join("");

	$results.html(`${header}${body}</tbody></table></div>`);
	$results.find(".historical-select-all").on("change", function () {
		$results.find(".historical-row:not(:disabled)").prop("checked", this.checked);
	});
}

function _link_selected_historical(frm, d) {
	const sales_orders = [];
	d.fields_dict.results.$wrapper.find(".historical-row:checked").each(function () {
		sales_orders.push($(this).attr("data-name"));
	});

	if (!sales_orders.length) {
		frappe.msgprint(__("Select at least one Sales Order to link."));
		return;
	}

	frappe.call({
		method: "nbs_customization.utils.placement.historical_link.link_historical_sales_orders",
		args: { contract: frm.doc.name, sales_orders: sales_orders },
		freeze: true,
		callback(r) {
			const result = r.message || {};
			d.hide();
			frappe.show_alert({
				message: __(
					"Linked {0} transaction(s): {1} sales order(s), {2} sales invoice(s), {3} delivery note(s).",
					[
						result.total || 0,
						result.sales_orders || 0,
						result.sales_invoices || 0,
						result.delivery_notes || 0,
					]
				),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}

function _show_dashboard_alert(frm) {
	if (!frm.doc.custom_instrument_placement_contract) return;

	const contract_link = frappe.utils.get_form_link(
		"Instrument Placement Contract",
		frm.doc.custom_instrument_placement_contract,
		true
	);
	frm.dashboard.add_comment(
		__("Linked to Placement Contract: {0} — {1}", [
			contract_link,
			frm.doc.custom_instrument_placement_contract,
		])
	);
}
