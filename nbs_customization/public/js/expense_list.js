// Copyright (c) 2024, NBS Solutions and contributors
// For license information, please see license.txt

frappe.listview_settings["Expense"] = {
	onload(listview) {
		listview.page.add_inner_button(
			__("Add Multiple Expenses"),
			() => open_bulk_expense_dialog(listview),
			null,
			"primary"
		);
	},
};

// ------------------------------------------------------------------ //
// Small helpers (public first, utilities at bottom)                    //
// ------------------------------------------------------------------ //

function open_bulk_expense_dialog(listview) {
	const company = frappe.defaults.get_user_default("Company");
	frappe.db
		.get_list("Expense Category", {
			fields: ["name", "is_accompanying_expense"],
			limit: 200,
		})
		.then((categories) => {
			const ctx = {
				company,
				category_map: new Map((categories || []).map((c) => [c.name, c])),
			};
			const dialog = new frappe.ui.Dialog({
				title: __("Add Multiple Expenses"),
				size: "extra-large",
				static: 1,
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
			dialog._rows = [];
			dialog._ctx = ctx;
			dialog.$wrapper.addClass("nbs-exp-bulk-dialog");
			ensure_bulk_styles();
			render_parent(dialog);
			dialog.show();
			dialog.get_close_btn().show();
		});
}

function render_parent(dialog) {
	const wrapper = dialog.fields_dict.expense_table_html.$wrapper;
	const rows = dialog._rows;
	const count = rows.length;
	const total = rows.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0);

	wrapper.html(`
		<div class="nbs-exp-head">
			<div>
				<div class="nbs-exp-title">${__("Expenses")}</div>
				<div class="text-muted">${__(
					"Add each expense, review the list, then submit them all in one go."
				)}</div>
			</div>
			<button class="btn btn-default btn-sm nbs-add-row-top">+ ${__("Add Row")}</button>
		</div>
		<div class="nbs-exp-table-wrap">
			<table class="table nbs-exp-table">
				<thead>
					<tr>
						<th class="nbs-c-idx">#</th>
						<th>${__("Date")}</th>
						<th>${__("Description")}</th>
						<th>${__("Category")}</th>
						<th>${__("Payee")}</th>
						<th>${__("Payment Method")}</th>
						<th>${__("Payment Type")}</th>
						<th>${__("Purchase Invoice")}</th>
						<th class="text-right">${__("Amount")}</th>
						<th class="nbs-c-act"></th>
					</tr>
				</thead>
				<tbody>
					${count ? rows.map((r, i) => row_html(r, i)).join("") : empty_state_html()}
				</tbody>
			</table>
		</div>
	`);

	wrapper.find(".nbs-add-row-top, .nbs-empty-add").on("click", () => {
		open_row_dialog(dialog, null);
	});
	wrapper.find("tr.nbs-exp-row").on("click", function (e) {
		if ($(e.target).closest(".nbs-row-del").length) return;
		open_row_dialog(dialog, parseInt($(this).data("idx"), 10));
	});
	wrapper.find("tr.nbs-exp-row").on("keydown", function (e) {
		// Only when the row itself is focused, so a focused action button keeps
		// its own Enter/Space activation.
		if (e.target !== this) return;
		if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
			e.preventDefault();
			open_row_dialog(dialog, parseInt($(this).data("idx"), 10));
		}
	});
	wrapper.find(".nbs-row-edit").on("click", function (e) {
		e.stopPropagation();
		open_row_dialog(dialog, parseInt($(this).data("idx"), 10));
	});
	wrapper.find(".nbs-row-del").on("click", function (e) {
		e.stopPropagation();
		const idx = parseInt($(this).data("idx"), 10);
		const target = dialog._rows[idx];
		frappe.confirm(
			__(`Delete expense <b>${esc(target.expense_description || "")}</b>?`),
			() => {
				dialog._rows.splice(idx, 1);
				render_parent(dialog);
			}
		);
	});

	dialog.fields_dict.summary_html.$wrapper.html(`
		<div class="nbs-exp-foot">
			<div class="nbs-exp-total-line">
				<span><b>${count}</b> ${count === 1 ? __("expense") : __("expenses")}</span>
				<span class="text-muted">·</span>
				<span>${__("Total")}</span>
				<span class="nbs-exp-total-amt">${frappe.format(total, { fieldtype: "Currency" })}</span>
			</div>
		</div>
	`);
	const primary = dialog.get_primary_btn();
	if (primary && primary.length) primary.prop("disabled", !count);
}

function open_row_dialog(parent_dialog, idx) {
	const ctx = parent_dialog._ctx;
	const editing = idx !== null && idx !== undefined ? parent_dialog._rows[idx] : null;
	const d = new frappe.ui.Dialog({
		title: editing ? __("Edit Expense Row") : __("Add Expense Row"),
		size: "large",
		fields: row_dialog_fields(editing),
		primary_action_label: editing ? __("Save") : __("Add"),
		primary_action(values) {
			return save_row(d, parent_dialog, idx, values, false);
		},
	});
	d._ctx = ctx;
	wire_row_dialog(d, editing);
	// "Add & Add Another" only makes sense when creating new rows.
	if (!editing) {
		d.add_custom_action(__("Add & Add Another"), () => {
			const values = d.get_values();
			if (!values) return;
			save_row(d, parent_dialog, idx, values, true);
		});
	}
	d.show();
	// Field defaults are applied on show, so re-run the conditional pass afterwards.
	if (d._sync_visibility) d._sync_visibility();
	d.$wrapper.on("shown.bs.modal.nbs-row", () => {
		if (d._sync_visibility) d._sync_visibility();
	});
	d.$wrapper.on("keydown.nbs-row", (e) => {
		if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
			e.preventDefault();
			d.get_primary_btn().trigger("click");
		}
	});
	d.$wrapper.on("hide.bs.modal.nbs-row", () => d.$wrapper.off(".nbs-row"));
	const footer = d.$wrapper.find(".modal-footer");
	if (footer.length && !footer.find(".nbs-row-hint").length) {
		const hint = editing ? __("Ctrl + Enter to save") : __("Ctrl + Enter to add");
		footer.prepend(
			`<div class="nbs-row-hint text-muted pull-left">${hint}</div>
			<div class="nbs-row-error text-danger pull-left"></div>`
		);
	}
}

async function save_row(d, parent_dialog, idx, values, keep_open) {
	await ensure_category_meta(d, values.expense_category);
	const errors = validate_row_values(d, values);
	if (errors.length) {
		show_row_errors(d, errors);
		return;
	}
	clear_row_errors(d);
	const row = await values_to_row(d, values);
	if (!row) return;
	if (idx !== null && idx !== undefined) parent_dialog._rows[idx] = row;
	else parent_dialog._rows.push(row);
	render_parent(parent_dialog);
	frappe.show_alert(
		{
			message: idx !== null && idx !== undefined ? __("Row updated.") : __("Expense added."),
			indicator: "green",
		},
		2
	);
	if (keep_open) {
		reset_row_dialog(d);
	} else {
		d.hide();
	}
}

// ------------------------------------------------------------------ //
// Child dialog: fields                                                 //
// ------------------------------------------------------------------ //

// Field order, labels, and 2-column layout mirror the New Expense form.
function row_dialog_fields(editing) {
	const today = frappe.datetime.get_today();
	const val = (key, fallback) => (editing ? editing[key] ?? fallback : fallback);
	return [
		{ fieldtype: "Section Break" },
		{
			fieldtype: "Data",
			fieldname: "expense_description",
			label: __("Expense Description"),
			reqd: 1,
			placeholder: __("e.g. Freight charge"),
			default: val("expense_description", ""),
		},
		{
			fieldtype: "Currency",
			fieldname: "amount",
			label: __("Paid Amount"),
			reqd: 1,
			default: val("amount", ""),
		},
		{
			fieldtype: "Data",
			fieldname: "payee",
			label: __("Payee"),
			reqd: 1,
			placeholder: __("e.g. DHL"),
			default: val("payee", ""),
		},
		{ fieldtype: "Column Break" },
		{
			fieldtype: "Date",
			fieldname: "expense_date",
			label: __("Expense Date"),
			reqd: 1,
			default: editing ? editing.expense_date : today,
		},
		{
			fieldtype: "Select",
			fieldname: "payment_type",
			label: __("Payment Type"),
			reqd: 1,
			options: ["Direct Payment", "Against Purchase Invoice"],
			default: editing ? editing.payment_type : "Direct Payment",
		},
		{
			fieldtype: "Link",
			fieldname: "expense_category",
			label: __("Expense Category"),
			options: "Expense Category",
			placeholder: __("Search category"),
			default: val("expense_category", ""),
		},
		{
			fieldtype: "Link",
			fieldname: "purchase_invoice",
			label: __("Purchase Invoice"),
			options: "Purchase Invoice",
			placeholder: __("Search purchase invoice"),
			default: val("purchase_invoice", ""),
		},
		{
			fieldtype: "Link",
			fieldname: "mode_of_payment",
			label: __("Payment Method"),
			options: "Mode of Payment",
			reqd: 1,
			placeholder: __("Search payment method"),
			default: val("mode_of_payment", ""),
			get_query() {
				return { filters: { enabled: 1 } };
			},
		},
		{ fieldtype: "Section Break", label: __("Payment Reference") },
		{
			fieldtype: "Data",
			fieldname: "reference_no",
			label: __("Cheque/Reference No"),
			description: __(
				"Cheque number or bank transfer reference. Required for Bank payment methods."
			),
			default: val("reference_no", ""),
		},
		{ fieldtype: "Column Break" },
		{
			fieldtype: "Date",
			fieldname: "reference_date",
			label: __("Cheque/Reference Date"),
			default: val("reference_date", ""),
		},
		{
			fieldtype: "Link",
			fieldname: "check_bank",
			label: __("Check Bank"),
			options: "Bank",
			default: val("check_bank", ""),
		},
		{ fieldtype: "Section Break", label: __("Accompanying Expense Details") },
		{
			fieldtype: "Check",
			fieldname: "is_accompanying",
			label: __("Is Accompanying Expense"),
			default: editing ? editing.is_accompanying || 0 : 0,
		},
		{
			fieldtype: "Select",
			fieldname: "expense_scope",
			label: __("Expense Scope"),
			options: ["Purchase Order", "Inbound Shipment"],
			default: editing && editing.expense_scope ? editing.expense_scope : "Purchase Order",
		},
		{
			fieldtype: "Link",
			fieldname: "linked_shipment",
			label: __("Linked Inbound Shipment"),
			options: "Inbound Shipment",
			default: val("linked_shipment", ""),
		},
		{
			fieldtype: "HTML",
			fieldname: "purchase_orders_html",
		},
		{ fieldtype: "Section Break" },
		{
			fieldtype: "Small Text",
			fieldname: "notes",
			label: __("Notes"),
			default: val("notes", ""),
		},
	];
}

function wire_row_dialog(d, editing) {
	const F = d.fields_dict;
	const company = d._ctx.company;
	d._resolved = editing
		? {
				account: editing.paid_from,
				is_check: !!editing.is_check,
				needs_ref: !!editing.needs_ref,
		  }
		: null;
	// Tracks the method whose account is being resolved, so a stale response
	// from an earlier selection cannot overwrite the current one.
	d._mop_req = editing ? editing.mode_of_payment : null;

	F.purchase_invoice.get_query = () => ({
		query: "nbs_customization.nbs_customization.doctype.expense.expense.get_purchase_invoices_search",
		filters: { company },
	});
	F.linked_shipment.get_query = () => ({
		query: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_shipments_search",
		filters: { company },
	});

	// Single source of truth for conditional visibility; mirrors the form's
	// toggle_payment_fields / toggle_accompanying_fields / set_reference_required.
	const sync_visibility = () => {
		const vals = read_values(F);
		const is_invoice = vals.payment_type === "Against Purchase Invoice";
		const acc = !!vals.is_accompanying;
		// Payment Type owns the Purchase Invoice / Expense Category pair — mutually
		// exclusive ONLY when not accompanying; accompanying always needs a category.
		const needs_category = !is_invoice || acc;
		const is_shipment = vals.expense_scope === "Inbound Shipment";

		toggle_field(d, "purchase_invoice", is_invoice);
		set_reqd(d, "purchase_invoice", is_invoice);

		toggle_field(d, "expense_category", needs_category);
		set_reqd(d, "expense_category", needs_category);
		// Accompanying expenses may only use accompanying-flagged categories.
		F.expense_category.get_query = () =>
			acc ? { filters: { is_accompanying_expense: 1 } } : {};

		const is_check = !!(d._resolved && d._resolved.is_check);
		toggle_field(d, "check_bank", is_check);
		set_reqd(d, "check_bank", is_check);

		toggle_field(d, "expense_scope", acc);
		toggle_field(d, "purchase_orders_html", acc && !is_shipment);
		toggle_field(d, "linked_shipment", acc && is_shipment);
		if (acc && !is_shipment && !d._po_controls.length) add_po_control(d, "");
	};
	d._sync_visibility = sync_visibility;

	// Hidden-when-inactive fields still render inputs (hidden flags removed),
	// but guard anyway — Dialog skips $input for unrendered controls.
	// Link selections fire awesomplete-selectcomplete, not change.
	const on_change = (name, fn) => {
		const c = F[name];
		if (c && c.$input) {
			c.$input.on("change", fn);
			c.$input.on("awesomplete-selectcomplete", fn);
		}
	};

	on_change("payment_type", () => {
		// Expense Category and Purchase Invoice are mutually exclusive; drop the
		// unused one. An accompanying expense keeps its category even on invoice pay.
		if (F.payment_type.get_value() === "Against Purchase Invoice") {
			if (!F.is_accompanying.get_value()) clear_category(d);
		} else {
			clear_purchase_invoice(d);
		}
		sync_visibility();
	});

	on_change("is_accompanying", () => {
		if (!F.is_accompanying.get_value()) {
			F.expense_scope.set_value("Purchase Order");
			clear_shipment(d);
			clear_po_controls(d);
		}
		sync_visibility();
	});

	on_change("expense_scope", () => {
		// Clear the link that no longer applies after a scope switch.
		if (F.expense_scope.get_value() === "Inbound Shipment") clear_po_controls(d);
		else clear_shipment(d);
		sync_visibility();
	});

	on_change("expense_category", () => {
		const name = F.expense_category.get_value();
		const meta = d._ctx.category_map.get(name);
		if (
			meta &&
			parseInt(meta.is_accompanying_expense || 0, 10) === 1 &&
			!F.is_accompanying.get_value()
		) {
			F.is_accompanying.set_value(1);
		}
		sync_visibility();
	});

	on_change("purchase_invoice", () => {
		const name = F.purchase_invoice.get_value();
		if (!name) {
			F.purchase_invoice.df.description = "";
			F.purchase_invoice.refresh();
			return;
		}
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.expense.expense.get_invoice_details",
			args: { purchase_invoice: name },
			callback(r) {
				if (!r.message) return;
				// Ignore a late response if the invoice changed while this was in flight.
				if (F.purchase_invoice.get_value() !== name) return;
				const pi = r.message;
				// Form parity: selecting a PI overwrites the amount with the outstanding.
				F.amount.set_value(pi.outstanding_amount);
				if (!`${F.payee.get_value() || ""}`.trim()) {
					F.payee.set_value(pi.supplier_name || pi.supplier);
				}
				F.purchase_invoice.df.description = `${__("Outstanding")}: ${frappe.format(
					pi.outstanding_amount,
					{ fieldtype: "Currency" }
				)}`;
				F.purchase_invoice.refresh();
				frappe.show_alert(
					{
						message: __("Outstanding: {0}", [
							frappe.format(pi.outstanding_amount, { fieldtype: "Currency" }),
						]),
						indicator: "blue",
					},
					5
				);
			},
		});
	});

	on_change("linked_shipment", () => {
		const name = F.linked_shipment.get_value();
		if (!name) {
			F.linked_shipment.df.description = "";
			F.linked_shipment.refresh();
			return;
		}
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_shipment_summary",
			args: { shipment_name: name },
			callback(r) {
				if (!r.message) return;
				const s = r.message;
				F.linked_shipment.df.description = `${s.pr_count} PR(s) | ${s.total_chargeable_weight} kg | ${s.status}`;
				F.linked_shipment.refresh();
			},
		});
	});

	on_change("mode_of_payment", () => {
		const method = F.mode_of_payment.get_value();
		d._mop_req = method;
		d._resolved = null;
		if (!method) {
			sync_visibility();
			return;
		}
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.expense.expense.get_payment_method_account",
			args: { mode_of_payment: method, company },
			callback(r) {
				// A newer selection superseded this request.
				if (d._mop_req !== method) return;
				if (!r.message) {
					sync_visibility();
					return;
				}
				const account =
					r.message.is_check && r.message.clearing_account_outward
						? r.message.clearing_account_outward
						: r.message.account;
				let needs_ref = !!r.message.is_check;
				d._resolved = { account, is_check: !!r.message.is_check, needs_ref };
				if (!r.message.is_check && account) {
					frappe.db.get_value("Account", account, "account_type", (ar) => {
						if (d._mop_req !== method || !d._resolved) return;
						needs_ref = !!ar && ar.account_type === "Bank";
						d._resolved.needs_ref = needs_ref;
						sync_visibility();
					});
					return;
				}
				sync_visibility();
			},
		});
	});

	// Multi-PO controls live in an HTML container (native Table fields crash in Dialogs).
	build_po_container(d);
	const seed_pos =
		editing && editing.purchase_orders
			? editing.purchase_orders.map((r) => r.purchase_order)
			: [];
	seed_pos.filter(Boolean).forEach((name) => add_po_control(d, name));

	// Resolve current method for edit mode so Save keeps paid_from.
	if (editing && editing.mode_of_payment && d._resolved) {
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.expense.expense.get_payment_method_account",
			args: { mode_of_payment: editing.mode_of_payment, company },
			callback(r) {
				if (!r.message) return;
				// Ignore a late response if the method changed while in flight.
				if (!d._resolved || F.mode_of_payment.get_value() !== editing.mode_of_payment)
					return;
				const account =
					r.message.is_check && r.message.clearing_account_outward
						? r.message.clearing_account_outward
						: r.message.account;
				d._resolved.account = account;
				d._resolved.is_check = !!r.message.is_check;
				d._resolved.needs_ref = !!r.message.is_check;
				if (!r.message.is_check && account) {
					const method = editing.mode_of_payment;
					frappe.db.get_value("Account", account, "account_type", (ar) => {
						if (d._mop_req !== method || !d._resolved) return;
						d._resolved.needs_ref = !!ar && ar.account_type === "Bank";
						sync_visibility();
					});
					return;
				}
				sync_visibility();
			},
		});
	}
	sync_visibility();
}

function read_values(F) {
	const vals = {};
	Object.keys(F).forEach((k) => {
		try {
			vals[k] = F[k].get_value();
		} catch (e) {
			vals[k] = null;
		}
	});
	return vals;
}

function set_reqd(d, fieldname, reqd) {
	const f = d.fields_dict[fieldname];
	if (!f) return;
	f.df.reqd = reqd ? 1 : 0;
	f.refresh();
}

function clear_purchase_invoice(d) {
	const f = d.fields_dict.purchase_invoice;
	if (!f || !f.get_value()) return;
	f.set_value("");
	f.df.description = "";
	f.refresh();
}

function clear_category(d) {
	const f = d.fields_dict.expense_category;
	if (!f || !f.get_value()) return;
	f.set_value("");
	f.refresh();
}

function clear_shipment(d) {
	const f = d.fields_dict.linked_shipment;
	if (!f) return;
	f.set_value("");
	f.df.description = "";
	f.refresh();
}

function clear_po_controls(d) {
	(d._po_controls || []).forEach((p) => p.wrap.remove());
	d._po_controls = [];
}

function build_po_container(d) {
	const F = d.fields_dict;
	d._po_controls = [];
	F.purchase_orders_html.$wrapper.html(`
		<div class="nbs-po-section">
			<label class="control-label">${__("Purchase Orders")}</label>
			<div class="nbs-po-list"></div>
			<button class="btn btn-xs btn-default nbs-po-add">+ ${__("Purchase Order")}</button>
		</div>
	`);
	F.purchase_orders_html.$wrapper.find(".nbs-po-add").on("click", () => add_po_control(d, ""));
}

function add_po_control(d, value) {
	const company = d._ctx.company;
	const list = d.fields_dict.purchase_orders_html.$wrapper.find(".nbs-po-list");
	const wrap = $(`<div class="nbs-po-row"></div>`);
	const ctrl_wrap = $(`<div class="nbs-po-ctrl"></div>`);
	const del = $(
		`<button class="btn btn-xs btn-default nbs-po-del" title="${__(
			"Remove"
		)}"><i class="fa fa-trash text-danger"></i></button>`
	);
	wrap.append(ctrl_wrap).append(del);
	list.append(wrap);
	const ctrl = frappe.ui.form.make_control({
		df: {
			fieldtype: "Link",
			options: "Purchase Order",
			placeholder: __("Search Purchase Order"),
			get_query: () => ({
				query: "nbs_customization.nbs_customization.doctype.expense.expense.get_purchase_orders_search",
				filters: { company },
			}),
			onchange() {
				// A Purchase Order may only appear once per row — drop a re-picked duplicate.
				const name = this.get_value();
				if (!name) return;
				const dup = d._po_controls.some(
					(p) => p.ctrl !== this && p.ctrl.get_value() === name
				);
				if (dup) {
					frappe.msgprint(__("Purchase Order {0} already added.", [name]));
					this.set_value("");
				}
			},
		},
		parent: ctrl_wrap,
		render_input: true,
	});
	ctrl.refresh();
	if (value) ctrl.set_value(value);
	const entry = { wrap, ctrl };
	d._po_controls.push(entry);
	del.on("click", () => {
		const i = d._po_controls.indexOf(entry);
		if (i > -1) d._po_controls.splice(i, 1);
		wrap.remove();
	});
}

function po_names(d) {
	return (d._po_controls || []).map((p) => p.ctrl.get_value()).filter(Boolean);
}

async function ensure_category_meta(d, name) {
	// The dialog only pre-loads the first 200 categories; a Link search can
	// still return one outside that slice, so resolve it before validating.
	if (!name || d._ctx.category_map.has(name)) return;
	try {
		const r = await frappe.db.get_value("Expense Category", name, "is_accompanying_expense");
		if (r && r.message) d._ctx.category_map.set(name, r.message);
	} catch (e) {
		/* leave uncached; the server stays the source of truth */
	}
}

function validate_row_values(d, values) {
	const errors = [];
	const required = ["expense_description", "expense_date", "mode_of_payment", "payee"];
	required.forEach((k) => {
		if (!values[k])
			errors.push({
				field: k,
				message: `${d.fields_dict[k].df.label} ${__("is required")}`,
			});
	});
	if (!(parseFloat(values.amount) > 0)) {
		errors.push({ field: "amount", message: __("Enter an amount above zero") });
	}
	const is_invoice = values.payment_type === "Against Purchase Invoice";
	const acc = !!values.is_accompanying;
	const is_shipment = values.expense_scope === "Inbound Shipment";
	const needs_category = !is_invoice || acc;
	if (needs_category && !values.expense_category) {
		errors.push({ field: "expense_category", message: __("Expense Category is required") });
	}
	if (needs_category && values.expense_category) {
		const meta = d._ctx.category_map.get(values.expense_category);
		const flagged = !!(meta && parseInt(meta.is_accompanying_expense || 0, 10) === 1);
		if (acc && !flagged) {
			errors.push({
				field: "expense_category",
				message: __("Use a category marked as an Accompanying Expense Category"),
			});
		} else if (!acc && flagged) {
			errors.push({
				field: "expense_category",
				message: __(
					"This category is marked as an Accompanying Expense Category. Tick Is Accompanying Expense."
				),
			});
		}
	}
	if (is_invoice && !values.purchase_invoice) {
		errors.push({ field: "purchase_invoice", message: __("Purchase Invoice is required") });
	}
	const po_list = po_names(d);
	if (acc && !is_shipment && !po_list.length) {
		errors.push({
			field: "purchase_orders_html",
			message: __("Add at least one Purchase Order"),
		});
	}
	if (po_list.length !== new Set(po_list).size) {
		errors.push({
			field: "purchase_orders_html",
			message: __(
				"Duplicate Purchase Order found. Each Purchase Order can only be added once."
			),
		});
	}
	if (acc && is_shipment && !values.linked_shipment) {
		errors.push({ field: "linked_shipment", message: __("Inbound Shipment is required") });
	}
	const needs_ref = !!(d._resolved && d._resolved.needs_ref);
	if (needs_ref && (!values.reference_no || !values.reference_date)) {
		errors.push({
			field: "reference_no",
			message: __("Cheque/Reference No and Cheque/Reference Date are mandatory"),
		});
	}
	if (d._resolved && d._resolved.is_check && !values.check_bank) {
		errors.push({
			field: "check_bank",
			message: __("Check Bank is mandatory for Check payments"),
		});
	}
	if (values.mode_of_payment && (!d._resolved || !d._resolved.account)) {
		errors.push({
			field: "mode_of_payment",
			message: __("No default account found for this payment method and company"),
		});
	}
	return errors;
}

async function values_to_row(d, values) {
	let resolved = d._resolved;
	if (!resolved && values.mode_of_payment) {
		try {
			const r = await frappe.call({
				method: "nbs_customization.nbs_customization.doctype.expense.expense.get_payment_method_account",
				args: { mode_of_payment: values.mode_of_payment, company: d._ctx.company },
			});
			if (r.message) {
				resolved = {
					account:
						r.message.is_check && r.message.clearing_account_outward
							? r.message.clearing_account_outward
							: r.message.account,
					is_check: !!r.message.is_check,
					needs_ref: !!r.message.is_check,
				};
				if (!r.message.is_check && resolved.account) {
					const ar = await frappe.db.get_value(
						"Account",
						resolved.account,
						"account_type"
					);
					resolved.needs_ref = !!ar.message && ar.message.account_type === "Bank";
				}
				d._resolved = resolved;
			}
		} catch (e) {
			/* submit will surface server errors */
		}
	}
	const po_list = po_names(d);
	const is_invoice = values.payment_type === "Against Purchase Invoice";
	const acc = !!values.is_accompanying;
	const needs_category = !is_invoice || acc;
	return {
		expense_description: `${values.expense_description || ""}`.trim(),
		expense_date: values.expense_date,
		amount: parseFloat(values.amount) || 0,
		expense_category: needs_category ? values.expense_category || null : null,
		mode_of_payment: values.mode_of_payment,
		paid_from: resolved ? resolved.account : null,
		is_check: resolved && resolved.is_check ? 1 : 0,
		needs_ref: resolved ? !!resolved.needs_ref : false,
		reference_no: `${values.reference_no || ""}`.trim(),
		reference_date: values.reference_date || null,
		check_bank: values.check_bank || null,
		payee: `${values.payee || ""}`.trim(),
		payment_type: is_invoice ? "Against Purchase Invoice" : "Direct Payment",
		purchase_invoice: is_invoice ? values.purchase_invoice || null : null,
		is_accompanying: acc ? 1 : 0,
		expense_scope: acc ? values.expense_scope : null,
		linked_purchase_order:
			acc && values.expense_scope === "Purchase Order" && po_list.length ? po_list[0] : null,
		purchase_orders: po_list.map((name) => ({ purchase_order: name })),
		linked_shipment:
			acc && values.expense_scope === "Inbound Shipment"
				? values.linked_shipment || null
				: null,
		notes: `${values.notes || ""}`.trim() || null,
		company: d._ctx.company,
	};
}

function reset_row_dialog(d) {
	const F = d.fields_dict;
	F.expense_description.set_value("");
	F.amount.set_value("");
	F.payee.set_value("");
	F.expense_category.set_value("");
	F.reference_no.set_value("");
	F.reference_date.set_value("");
	F.notes.set_value("");
	if (F.check_bank) F.check_bank.set_value("");
	if (F.purchase_invoice) F.purchase_invoice.set_value("");
	if (F.linked_shipment) F.linked_shipment.set_value("");
	clear_po_controls(d);
	if (d._sync_visibility) d._sync_visibility();
	F.expense_description.$input.focus();
}

// ------------------------------------------------------------------ //
// Submit (payload identical to previous inline implementation)          //
// ------------------------------------------------------------------ //

function submit_bulk_expenses(dialog, listview, company) {
	const expenses = dialog._rows || [];
	if (!expenses.length) {
		frappe.msgprint(__("Please add at least one expense row."));
		return;
	}
	const bad = expenses.find(
		(e) =>
			!e.expense_description ||
			!e.expense_date ||
			!(parseFloat(e.amount) > 0) ||
			(!e.expense_category && (e.payment_type === "Direct Payment" || e.is_accompanying)) ||
			!e.mode_of_payment ||
			!e.payee ||
			(e.payment_type === "Against Purchase Invoice" && !e.purchase_invoice) ||
			(e.is_accompanying &&
				e.expense_scope === "Purchase Order" &&
				!(e.purchase_orders || []).length) ||
			(e.is_accompanying && e.expense_scope === "Inbound Shipment" && !e.linked_shipment) ||
			(e.needs_ref && (!e.reference_no || !e.reference_date)) ||
			(e.is_check && !e.check_bank)
	);
	if (bad) {
		frappe.show_alert(
			{
				message: __("Please fix the highlighted rows before submitting."),
				indicator: "red",
			},
			5
		);
		return;
	}
	frappe.confirm(
		__(
			`Submit <b>${expenses.length}</b> expense(s)? Each will be individually validated and posted to the accounts.`
		),
		() => {
			dialog.hide();
			submit_expenses_sequentially(expenses, listview, company);
		}
	);
}

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
				<p class="text-muted mb-2">${__("Processing")} ${current} ${__("of")} ${total}...</p>
				<div class="progress">
					<div class="progress-bar progress-bar-striped progress-bar-animated" style="width: ${pct}%">${pct}%</div>
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
		const e = expenses[index];
		try {
			const payload = {
				doctype: "Expense",
				expense_description: e.expense_description,
				expense_date: e.expense_date,
				amount: e.amount,
				expense_category: e.expense_category,
				mode_of_payment: e.mode_of_payment,
				paid_from: e.paid_from,
				reference_no: e.reference_no,
				reference_date: e.reference_date,
				check_bank: e.check_bank,
				payee: e.payee,
				payment_type: e.payment_type,
				purchase_invoice: e.purchase_invoice,
				is_accompanying: e.is_accompanying ? 1 : 0,
				expense_scope: e.is_accompanying ? e.expense_scope : null,
				linked_purchase_order: e.linked_purchase_order,
				purchase_orders: e.purchase_orders,
				linked_shipment: e.linked_shipment,
				notes: e.notes,
				company: e.company,
			};
			const new_doc = await frappe.call({
				method: "frappe.client.insert",
				args: { doc: payload },
			});
			if (!new_doc.message) throw new Error("Failed to create expense document.");
			const submitted = await frappe.call({
				method: "frappe.client.submit",
				args: { doc: new_doc.message },
			});
			if (submitted.message) {
				results.success.push({
					name: submitted.message.name,
					description: e.expense_description,
					amount: e.amount,
				});
			}
		} catch (err) {
			let error_msg = err.message || err.toString();
			if (err.exc) {
				const lines = err.exc.trim().split("\n");
				error_msg = lines[lines.length - 1] || error_msg;
			}
			results.failed.push({
				description: e.expense_description,
				amount: e.amount,
				error: error_msg,
			});
		}
		process_next(index + 1);
	}
	process_next(0);
}

function show_bulk_results(results, listview) {
	const success_count = results.success.length;
	const failed_count = results.failed.length;
	let html = `<div class="p-3">`;
	if (success_count) {
		html += `
			<div class="alert alert-success mb-3">
				<strong><i class="fa fa-check-circle"></i> ${success_count} expense(s) submitted successfully.</strong>
			</div>
			<table class="table table-sm table-bordered mb-4">
				<thead class="thead-light"><tr><th>${__("Expense")}</th><th>${__("Description")}</th><th>${__(
			"Amount"
		)}</th></tr></thead>
				<tbody>
					${results.success
						.map(
							(r) => `<tr><td><a href="/app/expense/${r.name}" target="_blank">${
								r.name
							}</a></td>
								<td>${esc(r.description)}</td>
								<td>${frappe.format(r.amount, { fieldtype: "Currency" })}</td></tr>`
						)
						.join("")}
				</tbody>
			</table>`;
	}
	if (failed_count) {
		html += `
			<div class="alert alert-danger mb-3">
				<strong><i class="fa fa-times-circle"></i> ${failed_count} expense(s) failed.</strong>
				These were not posted. Please review and submit individually.
			</div>
			<table class="table table-sm table-bordered">
				<thead class="thead-light"><tr><th>${__("Description")}</th><th>${__("Amount")}</th><th>${__(
			"Reason"
		)}</th></tr></thead>
				<tbody>
					${results.failed
						.map(
							(r) => `<tr class="table-danger"><td>${esc(r.description)}</td>
								<td>${frappe.format(r.amount, { fieldtype: "Currency" })}</td>
								<td><small class="text-danger">${esc(r.error)}</small></td></tr>`
						)
						.join("")}
				</tbody>
			</table>`;
	}
	html += `</div>`;
	const results_dialog = new frappe.ui.Dialog({
		title: __("Bulk Expense Submission Results"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "results_html" }],
		primary_action_label: __("Close"),
		primary_action() {
			results_dialog.hide();
			listview.refresh();
		},
	});
	results_dialog.$wrapper.addClass("nbs-exp-results-dialog");
	results_dialog.fields_dict.results_html.$wrapper.html(html);
	results_dialog.show();
	results_dialog.get_close_btn().hide();
}

// ------------------------------------------------------------------ //
// Parent table markup + styles                                          //
// ------------------------------------------------------------------ //

function row_html(r, i) {
	const ref_line =
		r.reference_no || r.reference_date
			? `<div class="nbs-sub">${esc(or_dash(r.reference_no))} · ${esc(
					or_dash(fmt_date(r.reference_date))
			  )}</div>`
			: "";
	const type_pill =
		r.payment_type === "Against Purchase Invoice"
			? `<span class="nbs-pill nbs-pill-blue">${__("Invoice Payment")}</span>`
			: `<span class="nbs-pill">${__("Direct Payment")}</span>`;
	let invoice_cell = `<span class="text-muted">—</span>`;
	if (r.purchase_invoice) {
		const linked =
			r.is_accompanying &&
			(r.expense_scope === "Purchase Order" || r.expense_scope === "Inbound Shipment")
				? `<div><span class="nbs-pill nbs-pill-blue-light">${__(
						"Accompanying"
				  )}</span></div>`
				: "";
		invoice_cell = `<div class="nbs-trunc">${esc(r.purchase_invoice)}</div>${linked}`;
	}
	return `
		<tr class="nbs-exp-row" data-idx="${i}" tabindex="0" role="button" aria-label="${__(
		"Edit expense"
	)}">
			<td class="text-muted">${i + 1}</td>
			<td class="text-nowrap">${esc(fmt_date(r.expense_date))}</td>
			<td><div class="nbs-trunc nbs-w-desc" title="${esc(r.expense_description)}">${esc(
		r.expense_description
	)}</div></td>
			<td><div class="nbs-trunc nbs-w-cat" title="${esc(r.expense_category)}">${esc(
		r.expense_category
	)}</div></td>
			<td><div class="nbs-trunc nbs-w-payee" title="${esc(r.payee)}">${esc(r.payee)}</div></td>
			<td><div>${esc(r.mode_of_payment)}</div>${ref_line}</td>
			<td>${type_pill}</td>
			<td>${invoice_cell}</td>
			<td class="text-right text-nowrap"><b>${frappe.format(r.amount, {
				fieldtype: "Currency",
			})}</b></td>
			<td class="nbs-c-act">
				<span class="nbs-row-actions">
					<button class="btn btn-xs btn-default nbs-row-edit" data-idx="${i}" title="${__(
		"Edit"
	)}"><i class="fa fa-pencil"></i></button>
					<button class="btn btn-xs btn-default nbs-row-del" data-idx="${i}" title="${__(
		"Delete"
	)}"><i class="fa fa-trash text-danger"></i></button>
				</span>
			</td>
		</tr>`;
}

function empty_state_html() {
	return `
		<tr><td colspan="10">
			<div class="nbs-empty">
				<div class="nbs-empty-icon"><i class="fa fa-file-text-o"></i></div>
				<div class="nbs-empty-title">${__("No expenses added yet")}</div>
				<div class="text-muted">${__(
					"Add as many rows as you need. Nothing is created until you press Submit All."
				)}</div>
				<button class="btn btn-default btn-sm nbs-empty-add">+ ${__("Add Row")}</button>
			</div>
		</td></tr>`;
}

function toggle_field(d, fieldname, show) {
	const f = d.fields_dict[fieldname];
	if (!f) return;
	f.$wrapper.toggle(!!show);
}

function show_row_errors(d, errors) {
	clear_row_errors(d);
	errors.forEach((e) => {
		if (d.fields_dict[e.field]) {
			d.fields_dict[e.field].$wrapper.addClass("nbs-has-error");
			let hint = d.fields_dict[e.field].$wrapper.find(".nbs-err-hint");
			if (!hint.length)
				d.fields_dict[e.field].$wrapper.append(`<div class="nbs-err-hint"></div>`);
			d.fields_dict[e.field].$wrapper.find(".nbs-err-hint").text(e.message);
		}
	});
	d.$wrapper
		.find(".nbs-row-error")
		.text(
			errors.length === 1
				? __("1 required field needs attention")
				: __("{0} required fields need attention", [errors.length])
		);
}

function clear_row_errors(d) {
	d.$wrapper.find(".nbs-has-error").removeClass("nbs-has-error");
	d.$wrapper.find(".nbs-err-hint").remove();
	d.$wrapper.find(".nbs-row-error").text("");
}

function ensure_bulk_styles() {
	if (document.getElementById("nbs-exp-bulk-styles")) return;
	const css = `
		.nbs-exp-bulk-dialog .modal-dialog { max-width: min(1280px, 94vw); width: min(1280px, 94vw); }
		.nbs-exp-results-dialog .modal-dialog { max-width: min(1000px, 92vw); width: min(1000px, 92vw); }
		.nbs-exp-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
		.nbs-exp-title { font-size: 16px; font-weight: 600; }
		.nbs-exp-table-wrap { border: 1px solid #e5e7eb; border-radius: 10px; overflow-x: auto; }
		.nbs-exp-table { margin: 0; font-size: 13px; min-width: 980px; }
		.nbs-exp-table thead th { background: #16295e; color: #fff; font-weight: 600; border: 0 !important; white-space: nowrap; padding: 10px 12px; }
		.nbs-exp-table tbody td { padding: 10px 12px; vertical-align: middle; border-top: 1px solid #eef0f4; }
		.nbs-exp-table tbody tr:nth-child(even) td { background: #f5f8ff; }
		.nbs-exp-row { cursor: pointer; }
		.nbs-exp-row:hover td { background: #eaf1ff !important; }
		.nbs-trunc { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
		.nbs-w-desc { max-width: 180px; } .nbs-w-cat { max-width: 160px; } .nbs-w-payee { max-width: 140px; }
		.nbs-sub { color: #9aa1b2; font-size: 12px; }
		.nbs-pill { display: inline-block; padding: 2px 10px; border-radius: 999px; background: #f1f2f4; font-size: 12px; white-space: nowrap; }
		.nbs-pill-blue { background: #e8efff; color: #2450c8; }
		.nbs-pill-blue-light { background: #eef4ff; color: #16295e; margin-top: 4px; }
		.nbs-c-idx { width: 36px; } .nbs-c-act { width: 76px; }
		.nbs-row-actions { display: inline-flex; gap: 6px; opacity: 0; }
		.nbs-exp-row:hover .nbs-row-actions, .nbs-exp-row:focus-within .nbs-row-actions { opacity: 1; }
		.nbs-empty { text-align: center; padding: 56px 20px; }
		.nbs-empty-icon { width: 48px; height: 48px; border-radius: 50%; background: #f1f2f4; display: inline-flex; align-items: center; justify-content: center; font-size: 20px; color: #8a8f9e; margin-bottom: 12px; }
		.nbs-empty-title { font-weight: 600; font-size: 15px; margin-bottom: 4px; }
		.nbs-empty .btn { margin-top: 14px; }
		.nbs-exp-foot { display: flex; justify-content: space-between; align-items: center; }
		.nbs-exp-total-line { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
		.nbs-exp-total-amt, .nbs-exp-total-amt > div { display: inline-block; margin: 0; text-align: left; font-weight: 600; }
		.nbs-row-hint { margin-right: auto; padding-top: 6px; }
		.nbs-row-error { margin-left: 12px; padding-top: 6px; }
		.nbs-has-error input, .nbs-has-error .form-control { border-color: #e35b5b !important; }
		.nbs-err-hint { color: #d33; font-size: 12px; margin-top: 4px; }
		.nbs-po-row { display: flex; gap: 6px; align-items: center; margin-bottom: 4px; }
		.nbs-po-row:last-child { margin-bottom: 0; }
		.nbs-po-ctrl { flex: 1; }
		.nbs-po-ctrl .frappe-control, .nbs-po-ctrl .form-group { margin-bottom: 0 !important; }
		.nbs-po-add { margin-top: 6px; }
	`;
	$("<style id='nbs-exp-bulk-styles'>").html(css).appendTo("head");
}

// ------------------------------------------------------------------ //
// Tiny utilities                                                        //
// ------------------------------------------------------------------ //

function esc(v) {
	return `${v === null || v === undefined ? "" : v}`
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;");
}

function or_dash(v) {
	const s = `${v || ""}`.trim();
	return s || "—";
}

function fmt_date(v) {
	if (!v) return "—";
	const parts = `${v}`.split("-");
	if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`;
	return v;
}
