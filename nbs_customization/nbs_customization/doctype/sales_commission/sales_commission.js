// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

// ─────────────────────────────────────────────────────────────────────────────
//  Utility: Commission Amount Calculation
//  Mirrors the exact formula from the legacy calculateCommissionAmounts util.
// ─────────────────────────────────────────────────────────────────────────────
function calculate_commission_amounts(
	amount_received,
	additions,
	deductions,
	commission_rate,
	withholding_tax_rate,
) {
	// commission_rate and withholding_tax_rate arrive as percentages (e.g. 10, 3)
	// convert to decimals
	const cr = (commission_rate || 0) / 100;
	const wtr = (withholding_tax_rate || 0) / 100;

	const wht_on_invoice = amount_received * wtr;
	const actual_received = amount_received - wht_on_invoice;
	const wht_amount = actual_received * wtr;
	const base = Math.max(0, actual_received - wht_amount - (additions || 0));
	const gross = base * cr;
	const net = Math.max(0, gross - (deductions || 0));

	return {
		base_for_commission: parseFloat(base.toFixed(2)),
		gross_commission: parseFloat(gross.toFixed(2)),
		withholding_tax_amount: parseFloat(wht_amount.toFixed(2)),
		commission_payable: parseFloat(net.toFixed(2)),
	};
}

// ─────────────────────────────────────────────────────────────────────────────
//  Parent Form Events: Sales Commission
// ─────────────────────────────────────────────────────────────────────────────
frappe.ui.form.on("Sales Commission", {
	// ── Setup ────────────────────────────────────────────────────────────────

	setup(frm) {
		// Restrict paying_account to actual (non-group) bank/cash/payable accounts
		frm.set_query("customer", function () {
			return { filters: { disabled: 0 } };
		});
	},

	refresh(frm) {
		_set_form_indicators(frm);
		_add_custom_buttons(frm);
		_render_allocation_bar(frm);

		// Read-only visual cue on submitted / cancelled docs
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

	// ── Customer filter on sales invoice link ────────────────────────────────

	customer(frm) {
		// Clear existing commission sales when customer changes (draft only)
		if (
			frm.doc.docstatus === 0 &&
			frm.doc.commission_sales &&
			frm.doc.commission_sales.length > 0 &&
			frm.doc.commission_sales.some((row) => row.sale)
		) {
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
				() => {
					// Revert customer change — reload the saved value
					frm.reload_doc();
				},
			);
		} else {
			_apply_invoice_filter(frm);
		}
	},

	// ── Validate before save ─────────────────────────────────────────────────

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
	// ── Set invoice filter and auto-fill total_amount ─────────────────────

	commission_sales_add(frm, cdt, cdn) {
		_apply_invoice_filter(frm);
	},

	sale(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.sale) {
			frappe.model.set_value(cdt, cdn, "total_amount", 0);
			_recalculate_row(frm, cdt, cdn);
			return;
		}

		// Fetch the invoice grand_total to populate total_amount
		// (fetch_from in JSON also does this, but we need immediate reactivity)
		frappe.db.get_value("Sales Invoice", row.sale, ["grand_total", "customer"], (r) => {
			if (r) {
				frappe.model.set_value(cdt, cdn, "total_amount", r.grand_total || 0);
			}
			_recalculate_row(frm, cdt, cdn);
		});
	},

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

	withholding_tax(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.withholding_tax) {
			frappe.model.set_value(cdt, cdn, "withholding_tax_rate", 0);
			_recalculate_row(frm, cdt, cdn);
			return;
		}

		// Fetch WHT rate from the server (handles fiscal-year lookup)
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.sales_commission.sales_commission.get_wht_rate_for_category",
			args: { tax_withholding_category: row.withholding_tax },
			callback(r) {
				const rate = r.message || 0;
				frappe.model.set_value(cdt, cdn, "withholding_tax_rate", rate);
				_recalculate_row(frm, cdt, cdn);
			},
		});
	},

	withholding_tax_rate(frm, cdt, cdn) {
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
		const paid = row.paid_amount || 0;
		frappe.model.set_value(
			cdt,
			cdn,
			"remaining_due",
			Math.max(0, (row.allocated_amount || 0) - paid),
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

	frm.fields_dict.commission_sales.grid.update_docfield_property(
		"sale",
		"get_query",
		function () {
			if (!customer) {
				return {
					filters: {
						docstatus: 1,
						status: ["in", ["Paid"]],
					},
				};
			}
			return {
				filters: {
					customer: customer,
					docstatus: 1,
					status: ["in", ["Paid"]],
				},
			};
		},
	);
}

function _recalculate_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	const result = calculate_commission_amounts(
		row.total_amount || 0,
		row.additions || 0,
		row.deductions || 0,
		row.commission_rate || 0,
		row.withholding_tax_rate || 0,
	);

	frappe.model.set_value(cdt, cdn, "base_for_commission", result.base_for_commission);
	frappe.model.set_value(cdt, cdn, "gross_commission", result.gross_commission);
	frappe.model.set_value(cdt, cdn, "withholding_tax_amount", result.withholding_tax_amount);
	frappe.model.set_value(cdt, cdn, "commission_payable", result.commission_payable);

	_recalculate_all_totals(frm);
}

function _recalculate_all_totals(frm) {
	const rows = frm.doc.commission_sales || [];

	let total_amount = 0,
		total_additions = 0,
		total_deductions = 0;
	let total_base = 0,
		total_gross = 0,
		total_wht = 0,
		total_payable = 0;

	rows.forEach((r) => {
		total_amount += r.total_amount || 0;
		total_additions += r.additions || 0;
		total_deductions += r.deductions || 0;
		total_base += r.base_for_commission || 0;
		total_gross += r.gross_commission || 0;
		total_wht += r.withholding_tax_amount || 0;
		total_payable += r.commission_payable || 0;
	});

	frm.set_value("total_amount", parseFloat(total_amount.toFixed(2)));
	frm.set_value("total_additions", parseFloat(total_additions.toFixed(2)));
	frm.set_value("total_deductions", parseFloat(total_deductions.toFixed(2)));
	frm.set_value("total_base_for_commission", parseFloat(total_base.toFixed(2)));
	frm.set_value("total_gross_commission", parseFloat(total_gross.toFixed(2)));
	frm.set_value("total_withholding_tax_amount", parseFloat(total_wht.toFixed(2)));
	frm.set_value("total_commission_payable", parseFloat(total_payable.toFixed(2)));
	
	_render_allocation_bar(frm);
}

function _set_form_indicators(frm) {
	const payment_status = frm.doc.payment_status;
	const indicator_map = {
		Pending: "orange",
		Partial: "blue",
		Paid: "green",
		Cancelled: "red",
	};
	const color = indicator_map[payment_status] || "grey";
	frm.page.set_indicator(payment_status || __("Draft"), color);
}

function _add_custom_buttons(frm) {
	// Only show "Process Payout" button on submitted, not-fully-paid commissions
	if (
		frm.doc.docstatus === 1 &&
		frm.doc.payment_status !== "Paid" &&
		frm.doc.payment_status !== "Cancelled"
	) {
		frm.add_custom_button(
			__("Process Payout"),
			function () {
				frappe.new_doc("Commission Payout", {
					commission: frm.doc.name,
				});
			},
			__("Actions"),
		);
	}

	// Show payment summary in a dialog
	if (frm.doc.docstatus === 1) {
		frm.add_custom_button(
			__("View Payouts"),
			function () {
				frappe.set_route("List", "Commission Payout", { commission: frm.doc.name });
			},
			__("Actions"),
		);
	}
}

function format_currency(value) {
	return frappe.format(value, { fieldtype: "Currency" });
}

function _render_allocation_bar(frm) {
	const wrapper = frm.fields_dict.commission_recipients && frm.fields_dict.commission_recipients.$wrapper;
	if (!wrapper) return;

	if (!wrapper.find('.allocation-bar-container').length) {
		wrapper.prepend(`
			<div class="allocation-bar-container" style="margin-bottom: 5px; background: #e2e8f0; border-radius: 4px; overflow: hidden; height: 8px;">
				<div class="allocation-bar" style="height: 100%; width: 0%; transition: width 0.3s ease, background-color 0.3s ease;"></div>
			</div>
			<div class="allocation-text" style="font-size: 13px; margin-bottom: 15px; font-weight: 500;"></div>
		`);
	}

	const total_payable = frm.doc.total_commission_payable || 0;
	const total_allocated = (frm.doc.commission_recipients || []).reduce(
		(sum, r) => sum + (r.allocated_amount || 0), 0
	);

	let percentage = total_payable > 0 ? (total_allocated / total_payable) * 100 : 0;
	if (percentage > 100) percentage = 100;

	let color = "var(--text-color, #1f272e)";
	let bar_color = "var(--red-500, #e65252)";
	
	if (Math.abs(total_allocated - total_payable) < 0.01 && total_payable > 0) {
		color = "var(--green-600, #2f9d58)";
		bar_color = "var(--green-500, #28a745)";
	} else if (total_allocated < total_payable) {
		color = "var(--orange-600, #d97706)";
		bar_color = "var(--orange-500, #ff851b)";
	} else if (total_allocated > total_payable + 0.01) {
		color = "var(--red-600, #dc2626)";
		bar_color = "var(--red-500, #e65252)";
	}

	wrapper.find('.allocation-bar').css({
		width: percentage + '%',
		backgroundColor: bar_color
	});

	wrapper.find('.allocation-text').html(
		`Allocation: <span style="color: ${color}"><b>${format_currency(total_allocated)}</b></span> / <b>${format_currency(total_payable)}</b>`
	);
}
