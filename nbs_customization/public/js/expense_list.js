// Copyright (c) 2024, NBS Solutions and contributors
// For license information, please see license.txt

frappe.listview_settings["Expense"] = {
	onload(listview) {
		listview.page.add_inner_button(
			__("Add Multiple Expenses"),
			() => open_bulk_expense_dialog(listview),
			null,
			"primary",
		);
	},
};

function make_link_control(parent, df) {
	const control = frappe.ui.form.make_control({
		df,
		parent,
		render_input: true,
	});
	control._mount = parent;
	control.refresh();
	if (control.$input) {
		control.$input.addClass("form-control form-control-sm");
	}
	return control;
}

function set_control_enabled(control, enabled) {
	if (!control) return;
	if (typeof control.toggle_enable === "function") {
		control.toggle_enable(enabled);
	} else if (control.$input) {
		control.$input.prop("disabled", !enabled);
	}
}

function set_control_visible(control, visible) {
	if (!control) return;
	(control._mount || control.$wrapper || control.wrapper || $([])).toggle(!!visible);
}

function bind_control_change(control, handler) {
	if (!control || !control.$input) return;
	control.$input.on("change", handler);
	control.$input.on("awesomplete-selectcomplete", handler);
}

// ------------------------------------------------------------------ //
// Dialog                                                               //
// ------------------------------------------------------------------ //

function open_bulk_expense_dialog(listview) {
	const company = frappe.defaults.get_user_default("Company");

	Promise.all([
		// Expense Categories
		frappe.db.get_list("Expense Category", {
			fields: ["name", "expense_account", "is_accompanying_expense"],
			limit: 200,
		}),
	]).then(([categories]) => {
		const dialog = new frappe.ui.Dialog({
			title: __("Add Multiple Expenses"),
			size: "extra-large",
			fields: [
				{ fieldtype: "HTML", fieldname: "expense_table_html" },
				{ fieldtype: "Section Break" },
				{ fieldtype: "HTML", fieldname: "summary_html" },
			],
			primary_action_label: __("Submit All"),
			primary_action() {
				submit_bulk_expenses(dialog, listview, company);
			},
		});

		// True full-screen
		dialog.$wrapper.find(".modal-dialog").css({
			"max-width": "94vw",
			width: "94vw",
		});

		build_expense_table(dialog, categories, company);
		dialog.show();
	});
}

// ------------------------------------------------------------------ //
// Table builder                                                        //
// ------------------------------------------------------------------ //

function build_expense_table(dialog, categories, company) {
	const wrapper = dialog.fields_dict.expense_table_html.$wrapper;

	wrapper.html(`
		<div class="bulk-expense-wrapper" style="overflow-x: auto;">
			<table class="table table-bordered table-sm bulk-expense-table"
				style="min-width: 1600px; font-size: 12px;">
				<thead class="thead-light">
					<tr>
						<th style="min-width:160px;">${__("Description")} *</th>
						<th style="min-width:110px;">${__("Date")} *</th>
						<th style="min-width:110px;">${__("Amount")} *</th>
						<th style="min-width:160px;">${__("Category")} *</th>
						<th style="min-width:160px;">${__("Paying Account")} *</th>
						<th style="min-width:110px;">${__("Balance")}</th>
						<th style="min-width:110px;">${__("Payee")} *</th>
						<th style="min-width:155px;">${__("Payment Type")} *</th>
						<th style="min-width:185px;">${__("Purchase Invoice")}</th>
						<th style="min-width:80px;">${__("Accompanying")}</th>
						<th style="min-width:165px;">${__("Scope")}</th>
						<th style="min-width:200px;">${__("Linked Document")}</th>
						<th style="min-width:40px;"></th>
					</tr>
				</thead>
				<tbody id="bulk-expense-rows"></tbody>
			</table>
			<button class="btn btn-xs btn-secondary grid-add-row mt-2 mb-2" id="add-expense-row">
				<i class="fa fa-plus"></i> ${__("Add Row")}
			</button>
		</div>
	`);

	// Start with one empty row
	add_expense_row(wrapper, categories, company);

	wrapper.find("#add-expense-row").on("click", () => {
		add_expense_row(wrapper, categories, company);
	});

	// Store references for submit handler
	dialog._expense_wrapper = wrapper;
	dialog._categories = categories;
}

// ------------------------------------------------------------------ //
// Row builder                                                          //
// ------------------------------------------------------------------ //

function add_expense_row(wrapper, categories, company) {
	const tbody = wrapper.find("#bulk-expense-rows");
	const today = frappe.datetime.get_today();

	const category_meta_map = new Map((categories || []).map((c) => [c.name, c]));

	const row = $(`
		<tr class="expense-row">
			<!-- Description -->
			<td>
				<input type="text" class="form-control form-control-sm exp-description"
					placeholder="${__("e.g. Freight charge")}" required>
			</td>
			<!-- Date -->
			<td>
				<input type="date" class="form-control form-control-sm exp-date"
					value="${today}" required>
			</td>
			<!-- Amount -->
			<td>
				<input type="number" class="form-control form-control-sm exp-amount"
					placeholder="0.00" min="0" step="0.01" required>
			</td>
			<!-- Category -->
			<td>
				<div class="exp-category-control"></div>
			</td>
			<!-- Paying Account -->
			<td>
				<div class="exp-paying-account-control"></div>
			</td>
			<!-- Balance -->
			<td>
				<span class="exp-balance text-muted small">—</span>
			</td>
			<!-- Payee -->
			<td>
				<input type="text" class="form-control form-control-sm exp-payee"
					placeholder="${__("e.g. DHL")}" required>
			</td>
			<!-- Payment Type -->
			<td>
				<select class="form-control form-control-sm exp-payment-type" required>
					<option value="Direct Payment">${__("Direct Payment")}</option>
					<option value="Against Purchase Invoice">${__("Against Invoice")}</option>
				</select>
			</td>
			<!-- Purchase Invoice -->
			<td>
				<div class="exp-invoice-control"></div>
				<small class="exp-invoice-outstanding text-muted"></small>
			</td>
			<!-- Accompanying checkbox -->
			<td class="text-center">
				<input type="checkbox" class="exp-accompanying"
					style="width:16px; height:16px; margin-top:6px;">
			</td>
			<!-- Scope — hidden until accompanying checked -->
			<td class="td-scope">
				<select class="form-control form-control-sm exp-scope" disabled style="display:none;">
					<option value="Single Purchase Receipt">${__("Single Purchase Receipt")}</option>
					<option value="Inbound Shipment">${__("Inbound Shipment")}</option>
				</select>
			</td>
			<!-- Linked Document — PR or Shipment depending on scope -->
			<td class="td-linked-doc">
				<div class="exp-purchase-control" style="display:none;"></div>
				<div class="exp-shipment-control" style="display:none;"></div>
				<small class="exp-linked-info text-muted"></small>
			</td>
			<!-- Delete -->
			<td class="text-center">
				<button class="btn btn-xs btn-danger remove-row" style="margin-top:2px;">
					<i class="fa fa-trash"></i>
				</button>
			</td>
		</tr>
	`);

	const category_control = make_link_control(row.find(".exp-category-control"), {
		fieldtype: "Link",
		options: "Expense Category",
		reqd: 1,
		placeholder: __("Search Category"),
	});

	const paying_account_control = make_link_control(row.find(".exp-paying-account-control"), {
		fieldtype: "Link",
		options: "Account",
		reqd: 1,
		placeholder: __("Search Account"),
		get_query() {
			return {
				filters: {
					account_type: ["in", ["Cash", "Bank"]],
					company: company,
					is_group: 0,
				},
			};
		},
	});

	const invoice_control = make_link_control(row.find(".exp-invoice-control"), {
		fieldtype: "Link",
		options: "Purchase Invoice",
		placeholder: __("Search Purchase Invoice"),
		get_query() {
			return {
				filters: {
					docstatus: 1,
					company: company,
					status: ["not in", ["Paid", "Cancelled"]],
				},
			};
		},
	});
	set_control_enabled(invoice_control, false);

	const purchase_control = make_link_control(row.find(".exp-purchase-control"), {
		fieldtype: "Link",
		options: "Purchase Receipt",
		placeholder: __("Search Purchase Receipt"),
		get_query() {
			return { filters: { docstatus: 1, company: company } };
		},
	});
	set_control_enabled(purchase_control, false);
	set_control_visible(purchase_control, false);

	const shipment_control = make_link_control(row.find(".exp-shipment-control"), {
		fieldtype: "Link",
		options: "Inbound Shipment",
		placeholder: __("Search Inbound Shipment"),
		get_query() {
			return {
				query: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_shipments_search",
				filters: { company: company },
			};
		},
	});
	set_control_enabled(shipment_control, false);
	set_control_visible(shipment_control, false);

	row.data("controls", {
		category: category_control,
		paying_account: paying_account_control,
		invoice: invoice_control,
		purchase: purchase_control,
		shipment: shipment_control,
	});

	// ---------------------------------------------------------------- //
	// Payment Type toggle                                               //
	// ---------------------------------------------------------------- //
	row.find(".exp-payment-type").on("change", function () {
		const is_invoice = $(this).val() === "Against Purchase Invoice";
		set_control_enabled(invoice_control, is_invoice);
		if (!is_invoice) {
			invoice_control.set_value("");
			row.find(".exp-invoice-outstanding").text("");
		}
	});

	// ---------------------------------------------------------------- //
	// Invoice selected — prefill amount and payee                      //
	// ---------------------------------------------------------------- //
	bind_control_change(invoice_control, function () {
		const invoice_name = invoice_control.get_value();
		if (!invoice_name) {
			row.find(".exp-invoice-outstanding").text("");
			return;
		}
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.expense.expense.get_invoice_details",
			args: { purchase_invoice: invoice_name },
			callback(r) {
				if (!r.message) return;
				const pi = r.message;
				if (!parseFloat(row.find(".exp-amount").val())) {
					row.find(".exp-amount").val(pi.outstanding_amount);
				}
				if (!row.find(".exp-payee").val()?.trim()) {
					row.find(".exp-payee").val(pi.supplier);
				}
				row.find(".exp-invoice-outstanding").text(
					`Outstanding: ${frappe.format_value(pi.outstanding_amount, { fieldtype: "Currency" })}`,
				);
			},
		});
	});

	// ---------------------------------------------------------------- //
	// Category change — auto-check accompanying if tagged              //
	// ---------------------------------------------------------------- //
	bind_control_change(category_control, function () {
		const category_name = category_control.get_value();
		const is_acc = (category_meta_map.get(category_name)?.is_accompanying_expense || 0) == 1;
		if (is_acc) {
			row.find(".exp-accompanying").prop("checked", true).trigger("change");
		}
	});

	// ---------------------------------------------------------------- //
	// Accompanying toggle                                               //
	// ---------------------------------------------------------------- //
	row.find(".exp-accompanying").on("change", function () {
		const is_acc = $(this).is(":checked");
		const $scope = row.find(".exp-scope");

		if (is_acc) {
			$scope.show().prop("disabled", false);
			// Trigger scope change to show correct linked doc selector
			$scope.trigger("change");
		} else {
			$scope.hide().prop("disabled", true).val("Single Purchase Receipt");
			purchase_control.set_value("");
			set_control_enabled(purchase_control, false);
			set_control_visible(purchase_control, false);
			shipment_control.set_value("");
			set_control_enabled(shipment_control, false);
			set_control_visible(shipment_control, false);
			row.find(".exp-linked-info").text("");
		}
	});

	// ---------------------------------------------------------------- //
	// Scope toggle — show PR or Shipment selector                      //
	// ---------------------------------------------------------------- //
	row.find(".exp-scope").on("change", function () {
		const scope = $(this).val();
		const is_shipment = scope === "Inbound Shipment";

		set_control_visible(purchase_control, !is_shipment);
		set_control_enabled(purchase_control, !is_shipment);
		if (is_shipment) purchase_control.set_value("");

		set_control_visible(shipment_control, is_shipment);
		set_control_enabled(shipment_control, is_shipment);
		if (!is_shipment) shipment_control.set_value("");

		row.find(".exp-linked-info").text("");
	});

	// ---------------------------------------------------------------- //
	// Shipment selected — show summary info                            //
	// ---------------------------------------------------------------- //
	bind_control_change(shipment_control, function () {
		const shipment_name = shipment_control.get_value();
		if (!shipment_name) {
			row.find(".exp-linked-info").text("");
			return;
		}
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_shipment_summary",
			args: { shipment_name },
			callback(r) {
				if (!r.message) return;
				const s = r.message;
				row.find(".exp-linked-info").html(
					`${s.pr_count} PR(s) | ${flt(s.total_chargeable_weight, 2)} kg | <b>${s.status}</b>`,
				);
			},
		});
	});

	// ---------------------------------------------------------------- //
	// Balance fetch — on account change or date change                 //
	// ---------------------------------------------------------------- //
	bind_control_change(paying_account_control, function () {
		fetch_row_balance(row, today);
	});

	row.find(".exp-date").on("change", function () {
		// Re-fetch balance if account already selected
		if (paying_account_control.get_value()) {
			fetch_row_balance(row, row.find(".exp-date").val());
		}
	});

	// ---------------------------------------------------------------- //
	// Remove row                                                        //
	// ---------------------------------------------------------------- //
	row.find(".remove-row").on("click", function () {
		if (tbody.find(".expense-row").length > 1) {
			const controls = row.data("controls") || {};
			Object.values(controls).forEach((c) => {
				try {
					c?.$input?.off();
				} catch (e) {
					/* ignore */
				}
			});
			row.remove();
		} else {
			frappe.show_alert(
				{
					message: __("At least one row is required."),
					indicator: "orange",
				},
				3,
			);
		}
	});

	tbody.append(row);
}

// ------------------------------------------------------------------ //
// Balance helper                                                       //
// ------------------------------------------------------------------ //

function fetch_row_balance(row, fallback_date) {
	const account = row.data("controls")?.paying_account?.get_value();
	const date = row.find(".exp-date").val() || fallback_date;
	const balance_span = row.find(".exp-balance");

	if (!account) {
		balance_span.html("—").removeClass("text-danger text-success text-warning");
		return;
	}

	frappe.call({
		method: "nbs_customization.nbs_customization.doctype.expense.expense.get_account_balance",
		args: { account, date },
		callback(r) {
			const balance = r.message || 0;
			const formatted = frappe.format_value(balance, { fieldtype: "Currency" });
			const amount = parseFloat(row.find(".exp-amount").val()) || 0;

			let cls = "text-success";
			if (balance <= 0) cls = "text-danger";
			else if (amount && balance < amount) cls = "text-warning";

			balance_span
				.html(formatted)
				.removeClass("text-danger text-success text-warning text-muted")
				.addClass(cls);

			row.data("balance", balance);
		},
	});
}

// ------------------------------------------------------------------ //
// Submit                                                               //
// ------------------------------------------------------------------ //

function submit_bulk_expenses(dialog, listview, company) {
	const wrapper = dialog._expense_wrapper;
	const rows = wrapper.find(".expense-row");

	if (!rows.length) {
		frappe.msgprint(__("Please add at least one expense row."));
		return;
	}

	const expenses = [];
	let has_error = false;

	rows.each(function () {
		const row = $(this);
		const controls = row.data("controls") || {};
		const description = row.find(".exp-description").val()?.trim();
		const date = row.find(".exp-date").val();
		const amount = parseFloat(row.find(".exp-amount").val()) || 0;
		const category = controls.category?.get_value();
		const paying_account = controls.paying_account?.get_value();
		const payee = row.find(".exp-payee").val()?.trim();
		const payment_type = row.find(".exp-payment-type").val();
		const purchase_invoice = controls.invoice?.get_value() || null;
		const is_accompanying = row.find(".exp-accompanying").is(":checked");
		const scope = row.find(".exp-scope").val() || "Single Purchase Receipt";
		const linked_purchase =
			scope === "Single Purchase Receipt" ? controls.purchase?.get_value() || null : null;
		const linked_shipment =
			scope === "Inbound Shipment" ? controls.shipment?.get_value() || null : null;

		// --- Validation ---
		const missing_basic =
			!description ||
			!date ||
			!amount ||
			!category ||
			!paying_account ||
			!payee ||
			!payment_type;

		const missing_invoice = payment_type === "Against Purchase Invoice" && !purchase_invoice;

		const missing_linked =
			is_accompanying && scope === "Single Purchase Receipt" && !linked_purchase;

		const missing_shipment =
			is_accompanying && scope === "Inbound Shipment" && !linked_shipment;

		if (
			missing_basic ||
			amount <= 0 ||
			missing_invoice ||
			missing_linked ||
			missing_shipment
		) {
			row.addClass("table-danger");
			has_error = true;
			return;
		}

		row.removeClass("table-danger");

		expenses.push({
			expense_description: description,
			expense_date: date,
			amount,
			expense_category: category,
			paying_account,
			payee,
			payment_type,
			purchase_invoice,
			is_accompanying: is_accompanying ? 1 : 0,
			expense_scope: is_accompanying ? scope : null,
			linked_purchase,
			linked_shipment,
			company,
		});
	});

	if (has_error) {
		frappe.show_alert(
			{
				message: __("Please fix the highlighted rows before submitting."),
				indicator: "red",
			},
			5,
		);
		return;
	}

	frappe.confirm(
		__(`Submit <b>${expenses.length}</b> expense(s)? Each will be individually
			validated and posted to the accounts.`),
		function () {
			dialog.hide();
			submit_expenses_sequentially(expenses, listview);
		},
	);
}

// ------------------------------------------------------------------ //
// Sequential submission with progress                                 //
// ------------------------------------------------------------------ //

function submit_expenses_sequentially(expenses, listview) {
	const total = expenses.length;
	const results = { success: [], failed: [] };

	const progress_dialog = new frappe.ui.Dialog({
		title: __("Submitting Expenses..."),
		fields: [{ fieldtype: "HTML", fieldname: "progress_html" }],
	});
	progress_dialog.show();
	progress_dialog.get_close_btn().hide();

	function update_progress(current) {
		const pct = Math.round((current / total) * 100);
		progress_dialog.fields_dict.progress_html.$wrapper.html(`
			<div class="p-3">
				<p class="text-muted mb-2">
					${__("Processing")} ${current} ${__("of")} ${total}...
				</p>
				<div class="progress">
					<div class="progress-bar progress-bar-striped progress-bar-animated"
						style="width: ${pct}%">${pct}%
					</div>
				</div>
			</div>
		`);
	}

	async function process_next(index) {
		if (index >= total) {
			progress_dialog.hide();
			show_bulk_results(results, listview);
			return;
		}

		update_progress(index + 1);
		const expense_data = expenses[index];

		try {
			const new_doc = await frappe.call({
				method: "frappe.client.insert",
				args: { doc: { doctype: "Expense", ...expense_data } },
			});
			if (!new_doc.message) throw new Error("Failed to create expense document.");

			const submitted = await frappe.call({
				method: "frappe.client.submit",
				args: { doc: new_doc.message },
			});
			if (submitted.message) {
				results.success.push({
					name: submitted.message.name,
					description: expense_data.expense_description,
					amount: expense_data.amount,
				});
			}
		} catch (err) {
			let error_msg = err.message || err.toString();
			if (err.exc) {
				const lines = err.exc.trim().split("\n");
				error_msg = lines[lines.length - 1] || error_msg;
			}
			results.failed.push({
				description: expense_data.expense_description,
				amount: expense_data.amount,
				error: error_msg,
			});
		}

		process_next(index + 1);
	}

	process_next(0);
}

// ------------------------------------------------------------------ //
// Results                                                              //
// ------------------------------------------------------------------ //

function show_bulk_results(results, listview) {
	const success_count = results.success.length;
	const failed_count = results.failed.length;

	let html = `<div class="p-3">`;

	if (success_count) {
		html += `
			<div class="alert alert-success mb-3">
				<strong><i class="fa fa-check-circle"></i>
				${success_count} expense(s) submitted successfully.</strong>
			</div>
			<table class="table table-sm table-bordered mb-4">
				<thead class="thead-light">
					<tr>
						<th>${__("Expense")}</th>
						<th>${__("Description")}</th>
						<th>${__("Amount")}</th>
					</tr>
				</thead>
				<tbody>
					${results.success
						.map(
							(r) => `
						<tr>
							<td><a href="/app/expense/${r.name}" target="_blank">${r.name}</a></td>
							<td>${r.description}</td>
							<td>${frappe.format_value(r.amount, { fieldtype: "Currency" })}</td>
						</tr>
					`,
						)
						.join("")}
				</tbody>
			</table>
		`;
	}

	if (failed_count) {
		html += `
			<div class="alert alert-danger mb-3">
				<strong><i class="fa fa-times-circle"></i>
				${failed_count} expense(s) failed.</strong>
				These were not posted. Please review and submit individually.
			</div>
			<table class="table table-sm table-bordered">
				<thead class="thead-light">
					<tr>
						<th>${__("Description")}</th>
						<th>${__("Amount")}</th>
						<th>${__("Reason")}</th>
					</tr>
				</thead>
				<tbody>
					${results.failed
						.map(
							(r) => `
						<tr class="table-danger">
							<td>${r.description}</td>
							<td>${frappe.format_value(r.amount, { fieldtype: "Currency" })}</td>
							<td><small class="text-danger">${r.error}</small></td>
						</tr>
					`,
						)
						.join("")}
				</tbody>
			</table>
		`;
	}

	html += `</div>`;

	const results_dialog = new frappe.ui.Dialog({
		title: __("Bulk Expense Submission Results"),
		fields: [{ fieldtype: "HTML", fieldname: "results_html" }],
		primary_action_label: __("Close"),
		primary_action() {
			results_dialog.hide();
			listview.refresh();
		},
	});
	results_dialog.fields_dict.results_html.$wrapper.html(html);
	results_dialog.show();
	results_dialog.get_close_btn().hide();
}
