// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

// ─────────────────────────────────────────────────────────────────────────────
//  Parent Form Events: Sales Commission
// ─────────────────────────────────────────────────────────────────────────────
frappe.ui.form.on("Sales Commission", {
	setup(frm) {
		frm.set_query("customer", () => ({ filters: { disabled: 0 } }));
		frm.set_query("cost_center", () => ({
			filters: {
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
				is_group: 0,
			},
		}));
	},

	refresh(frm) {
		_add_custom_buttons(frm);
		_render_allocation_bar(frm);

		if (frm.doc.docstatus === 1) {
			frm.set_intro(
				__(
					"This commission has been <b>approved (submitted)</b>. Payouts can now be processed.",
				),
				"green",
			);
		} else if (frm.doc.docstatus === 2) {
			frm.set_intro(__("This commission has been <b>cancelled</b>."), "red");
		}
	},

	company(frm) {
		frm.set_value("cost_center", null);
		frm.refresh_fields(["cost_center"]);
	},

	customer(frm) {
		const has_entries = (frm.doc.commission_sales || []).some((r) => r.sale);
		if (frm.doc.docstatus === 0 && has_entries) {
			frappe.confirm(
				__(
					"Changing the customer will clear all existing Commission Sale entries. Continue?",
				),
				() => {
					frm.clear_table("commission_sales");
					frm.refresh_field("commission_sales");
					_recalculate_all_totals(frm);
					_apply_invoice_filter(frm);
				},
				() => frm.reload_doc(),
			);
		} else {
			_apply_invoice_filter(frm);
		}
	},

	validate(frm) {
		_recalculate_all_totals(frm);

		const total_allocated = (frm.doc.commission_recipients || []).reduce(
			(sum, r) => sum + (r.allocated_amount || 0),
			0,
		);
		const total_payable = frm.doc.total_commission_payable || 0;

		if (total_allocated > total_payable + 0.01) {
			frappe.msgprint({
				title: __("Allocation Mismatch"),
				message: __(
					"Total Allocated Amount ({0}) exceeds Total Commission Payable ({1}). Please adjust.",
					[format_currency(total_allocated), format_currency(total_payable)],
				),
				indicator: "red",
			});
			frappe.validated = false;
		}
	},
});

// ─────────────────────────────────────────────────────────────────────────────
//  Child Table Events: Commission Sale Entry
// ─────────────────────────────────────────────────────────────────────────────
frappe.ui.form.on("Commission Sale Entry", {
	commission_sales_add(frm) {
		_apply_invoice_filter(frm);
	},

	// ── Invoice selected ─────────────────────────────────────────────────────
	// One server round-trip fetches: grand_total + WHT flag + WHT rate from
	// the invoice's Sales Taxes and Charges table (what ERPNext actually used).
	sale(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (!row.sale) {
			frappe.model.set_value(cdt, cdn, "total_amount", 0);
			frappe.model.set_value(cdt, cdn, "withholding_tax", "");
			frappe.model.set_value(cdt, cdn, "withholding_tax_rate", 0);
			_recalculate_row(frm, cdt, cdn);
			return;
		}

		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.sales_commission.sales_commission.get_invoice_details_for_commission",
			args: { invoice: row.sale },
			callback(r) {
				const d = r.message || {};

				frappe.model.set_value(cdt, cdn, "total_amount", d.grand_total || 0);

				if (d.consider_for_wht && d.wht_category) {
					frappe.model.set_value(cdt, cdn, "withholding_tax", d.wht_category);
					frappe.model.set_value(cdt, cdn, "withholding_tax_rate", d.wht_rate || 0);
					// Store the EXACT amount ERPNext computed — used directly in
					// the commission base formula (not recomputed from the rate).
					frappe.model.set_value(
						cdt,
						cdn,
						"withholding_tax_amount",
						d.wht_amount_on_inv || 0,
					);
				} else {
					frappe.model.set_value(cdt, cdn, "withholding_tax", "");
					frappe.model.set_value(cdt, cdn, "withholding_tax_rate", 0);
					frappe.model.set_value(cdt, cdn, "withholding_tax_amount", 0);
				}

				_recalculate_row(frm, cdt, cdn);
			},
		});
	},

	// Recalculate whenever any input changes
	total_amount(frm, cdt, cdn) {
		_recalculate_row(frm, cdt, cdn);
	},
	additions(frm, cdt, cdn) {
		_recalculate_row(frm, cdt, cdn);
	},
	deductions(frm, cdt, cdn) {
		_recalculate_row(frm, cdt, cdn);
	},
	commission_rate(frm, cdt, cdn) {
		_recalculate_row(frm, cdt, cdn);
	},
	commission_sales_remove(frm) {
		_recalculate_all_totals(frm);
	},
});

// ─────────────────────────────────────────────────────────────────────────────
//  Child Table Events: Commission Recipient
// ─────────────────────────────────────────────────────────────────────────────
frappe.ui.form.on("Commission Recipient", {
	allocated_amount(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(
			cdt,
			cdn,
			"remaining_due",
			Math.max(0, (row.allocated_amount || 0) - (row.paid_amount || 0)),
		);
		_render_allocation_bar(frm);
	},
	commission_recipients_remove(frm) {
		_render_allocation_bar(frm);
	},
});

// ─────────────────────────────────────────────────────────────────────────────
//  Private helpers
// ─────────────────────────────────────────────────────────────────────────────

function _apply_invoice_filter(frm) {
	const customer = frm.doc.customer;
	frm.fields_dict.commission_sales.grid.update_docfield_property("sale", "get_query", () => ({
		query: "nbs_customization.nbs_customization.doctype.sales_commission.sales_commission.get_invoices_for_customer",
		filters: { customer: customer },
	}));
}

function _recalculate_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	frappe.call({
		method: "nbs_customization.nbs_customization.doctype.sales_commission.sales_commission.calculate_commission_row",
		args: {
			grand_total: row.total_amount || 0,
			wht_amount: row.withholding_tax_amount || 0,
			additions: row.additions || 0,
			deductions: row.deductions || 0,
			commission_rate: row.commission_rate || 0,
		},
		callback(r) {
			const result = r.message || {};
			// withholding_tax_amount is an INPUT — do not overwrite it here.
			frappe.model.set_value(cdt, cdn, "base_for_commission", result.base_for_commission);
			frappe.model.set_value(cdt, cdn, "gross_commission", result.gross_commission);
			frappe.model.set_value(cdt, cdn, "commission_payable", result.commission_payable);
			_recalculate_all_totals(frm);
		},
	});
}

function _recalculate_all_totals(frm) {
	const rows = frm.doc.commission_sales || [];

	const t = rows.reduce(
		(acc, r) => {
			acc.total_amount += r.total_amount || 0;
			acc.total_additions += r.additions || 0;
			acc.total_deductions += r.deductions || 0;
			acc.total_base_for_commission += r.base_for_commission || 0;
			acc.total_gross_commission += r.gross_commission || 0;
			acc.total_withholding_tax_amount += r.withholding_tax_amount || 0;
			acc.total_commission_payable += r.commission_payable || 0;
			return acc;
		},
		{
			total_amount: 0,
			total_additions: 0,
			total_deductions: 0,
			total_base_for_commission: 0,
			total_gross_commission: 0,
			total_withholding_tax_amount: 0,
			total_commission_payable: 0,
		},
	);

	Object.entries(t).forEach(([k, v]) => frm.set_value(k, parseFloat(v.toFixed(2))));
	_render_allocation_bar(frm);
}

function _add_custom_buttons(frm) {
	if (frm.doc.docstatus === 1 && !["Paid", "Cancelled"].includes(frm.doc.payment_status)) {
		frm.add_custom_button(
			__("Process Payout"),
			() => frappe.new_doc("Commission Payout", { commission: frm.doc.name }),
			__("Actions"),
		);
	}
	if (frm.doc.docstatus === 1) {
		frm.add_custom_button(
			__("View Payouts"),
			() => frappe.set_route("List", "Commission Payout", { commission: frm.doc.name }),
			__("Actions"),
		);
	}
}

function format_currency(value) {
	return frappe.format(value, { fieldtype: "Currency" });
}

function _render_allocation_bar(frm) {
	const wrapper = frm.fields_dict.commission_recipients?.$wrapper;
	if (!wrapper) return;

	if (!wrapper.find(".allocation-bar-container").length) {
		wrapper.prepend(`
			<div class="allocation-bar-container" style="margin-bottom:5px;background:#e2e8f0;border-radius:4px;overflow:hidden;height:8px;">
				<div class="allocation-bar" style="height:100%;width:0%;transition:width .3s ease,background-color .3s ease;"></div>
			</div>
			<div class="allocation-text" style="font-size:13px;margin-bottom:15px;font-weight:500;"></div>
		`);
	}

	const total_payable = frm.doc.total_commission_payable || 0;
	const total_allocated = (frm.doc.commission_recipients || []).reduce(
		(sum, r) => sum + (r.allocated_amount || 0),
		0,
	);

	const pct = total_payable > 0 ? Math.min(100, (total_allocated / total_payable) * 100) : 0;
	const exact = Math.abs(total_allocated - total_payable) < 0.01 && total_payable > 0;
	const over = total_allocated > total_payable + 0.01;

	const bar = exact
		? "var(--green-500,#28a745)"
		: over
			? "var(--red-500,#e65252)"
			: "var(--orange-500,#ff851b)";
	const text = exact
		? "var(--green-600,#2f9d58)"
		: over
			? "var(--red-600,#dc2626)"
			: "var(--orange-600,#d97706)";

	wrapper.find(".allocation-bar").css({ width: pct + "%", backgroundColor: bar });
	wrapper
		.find(".allocation-text")
		.html(
			`Allocation: <span style="color:${text}"><b>${format_currency(total_allocated)}</b></span> / <b>${format_currency(total_payable)}</b>`,
		);
}
