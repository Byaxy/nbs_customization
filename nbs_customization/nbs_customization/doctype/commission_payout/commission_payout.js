// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

// ─────────────────────────────────────────────────────────────────────────────
//  Commission Payout Form
// ─────────────────────────────────────────────────────────────────────────────
frappe.ui.form.on("Commission Payout", {
	// ── Setup: static filters ────────────────────────────────────────────────

	setup(frm) {
		frm.set_query("paying_account", () => ({
			filters: {
				account_type: ["in", ["Cash", "Bank"]],
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
				is_group: 0,
				disabled: 0,
			},
		}));
		frm.set_query("expense_category", () => ({
			filters: {
				is_accompanying_expense: 0,
			},
		}));
		frm.set_query("cost_center", () => ({
			filters: {
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
				is_group: 0,
			},
		}));
		frm.set_query("commission_recipient", function () {
			if (!frm.doc.commission) {
				return { filters: { name: "__nonexistent__" } };
			}
			return {
				query: "nbs_customization.nbs_customization.doctype.commission_payout.commission_payout.commission_recipient_query",
				filters: {
					commission: frm.doc.commission,
				},
			};
		});

		// Commission must be submitted and not fully paid
		frm.set_query("commission", function () {
			return {
				filters: {
					docstatus: 1,
					payment_status: ["not in", ["Paid", "Cancelled"]],
				},
			};
		});
	},

	// ── Refresh ──────────────────────────────────────────────────────────────

	refresh(frm) {
		if (frm.doc.commission_recipient) {
			_load_recipient_details(frm, false);
		} else {
			_clear_recipient_info_panel(frm);
		}

		if (frm.doc.docstatus === 1) {
			frm.set_intro(
				__("This payout has been <b>submitted</b> and a Journal Entry has been posted."),
				"green",
			);
		} else if (frm.doc.docstatus === 2) {
			frm.set_intro(
				__(
					"This payout has been <b>cancelled</b> and the Journal Entry has been reversed.",
				),
				"red",
			);
		}

		// Show link to Journal Entry if exists
		if (frm.doc.journal_entry && frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("View Journal Entry"),
				function () {
					frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
				},
				__("Links"),
			);
		}
	},

	company(frm) {
		frm.set_value("paying_account", null);
		frm.set_value("cost_center", null);
		frm.refresh_fields(["paying_account", "cost_center"]);
	},

	// ── Commission selected ──────────────────────────────────────────────────

	commission(frm) {
		frm.set_value("commission_recipient", "");
		frm.set_value("sales_person", "");
		frm.set_value("amount_to_pay", 0);
		_clear_recipient_info_panel(frm);
	},

	// ── Recipient selected ───────────────────────────────────────────────────
	commission_recipient(frm) {
		if (frm.doc.commission_recipient) {
			_load_recipient_details(frm, true);
		} else {
			_clear_recipient_info_panel(frm);
			frm.set_value("amount_to_pay", 0);
		}
	},

	// ── Amount validation (live) ─────────────────────────────────────────────

	amount_to_pay(frm) {
		_validate_amount_live(frm);
	},

	paying_account(frm) {
		fetch_account_balance(frm);
	},
	payout_date(frm) {
		fetch_account_balance(frm);
	},

	// ── Before submit: final client-side gate ────────────────────────────────

	before_submit(frm) {
		const amount = flt(frm.doc.amount_to_pay);
		const remaining = flt(frm._recipient_remaining_due);

		if (amount <= 0) {
			frappe.msgprint({
				title: __("Invalid Amount"),
				message: __("Amount To Pay must be greater than zero."),
				indicator: "red",
			});
			frappe.validated = false;
			return;
		}

		if (frm._recipient_remaining_due !== undefined && amount > remaining + 0.01) {
			frappe.msgprint({
				title: __("Amount Exceeds Remaining Due"),
				message: __(
					"Amount To Pay ({0}) exceeds the Remaining Due ({1}) for this recipient.",
					[format_currency(amount), format_currency(remaining)],
				),
				indicator: "red",
			});
			frappe.validated = false;
			return;
		}
	},
});

// ─────────────────────────────────────────────────────────────────────────────
//  Private helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * After a recipient is selected, load their payment details and:
 * - Show an informational panel (allocated / paid / remaining)
 * - Pre-fill amount_to_pay ONLY if force_fill is true or field is empty
 */
function _load_recipient_details(frm, force_fill = false) {
	if (!frm.doc.commission_recipient) return;

	frappe.call({
		method: "nbs_customization.nbs_customization.doctype.commission_payout.commission_payout.get_recipient_summary",
		args: {
			recipient: frm.doc.commission_recipient,
		},
		callback: function (r) {
			if (!r.message) return;

			const data = r.message;

			// Cache for validation
			frm._recipient_remaining_due = flt(data.remaining_due);

			// ALWAYS update amount if:
			// - forced OR
			// - current amount is zero OR
			// - exceeds remaining (fix stale values)
			if (
				frm.doc.docstatus === 0 &&
				(
					force_fill ||
					!frm.doc.amount_to_pay ||
					frm.doc.amount_to_pay > data.remaining_due
				)
			) {
				frm.set_value("amount_to_pay", flt(data.remaining_due));
			}

			_render_recipient_info_panel(frm, data);
		},
	});
}

function _render_recipient_info_panel(frm, data) {
	const status_colors = {
		"Pending": "#f59e0b",
		"Partial": "#3b82f6",
		"Paid": "#10b981",
		"Cancelled": "#ef4444",
	};

	const color = status_colors[data.payment_status] || "#6b7280";

	const card = (label, value, highlight = false) => `
		<div style="
			flex:1;
			background:white;
			border-radius:10px;
			padding:12px 14px;
			box-shadow:0 2px 8px rgba(0, 0, 0, 0.25);
			display:flex;
			flex-direction:column;
			gap:4px;
		">
			<div style="
				font-size:11px;
				color:#6b7280;
				text-transform:uppercase;
				letter-spacing:0.4px;
			">
				${label}
			</div>
			<div style="
				font-size:${highlight ? "16px" : "14px"};
				font-weight:600;
				color:${highlight ? "#111827" : "#374151"};
			">
				${value}
			</div>
		</div>
	`;

	const html = `
		<div style="
			display:flex;
			flex-direction:column;
			gap:10px;
			margin-top:15px;
			margin-bottom:15px;
		">

			<!-- Header -->
			<div style="
				display:flex;
				justify-content:space-between;
				align-items:center;
			">
				<div style="font-weight:600; font-size:14px;">
					${data.sales_person}
				</div>
				<div style="
					background:${color}15;
					color:${color};
					padding:4px 10px;
					border-radius:20px;
					font-size:12px;
					font-weight:600;
				">
					${__(data.payment_status)}
				</div>
			</div>

			<!-- Cards -->
			<div style="display:flex; gap:20px;">
				${card(__("Allocated"), badge(format_currency(data.allocated_amount), "#111827"))}
				${card(__("Paid So Far"), badge(format_currency(data.paid_amount), get_paid_color(data.paid_amount, data.allocated_amount)))}
				${card(__("Remaining Due"), badge(format_currency(data.remaining_due), get_remaining_color(data.remaining_due, data.allocated_amount)))}
				${card(__("Status"), badge(data.payment_status, color))}
			</div>
		</div>
	`;

	if (frm.dashboard) {
		frm.dashboard.reset();
		frm.dashboard.add_section(html);
		frm.dashboard.show();
	}
}

function _clear_recipient_info_panel(frm) {
	frm._recipient_remaining_due = 0;
	if (frm.dashboard) {
		frm.dashboard.reset();
		frm.dashboard.hide();
	}
}

function _validate_amount_live(frm) {
	const amount = flt(frm.doc.amount_to_pay);
	const remaining = flt(frm._recipient_remaining_due);

	if (frm.doc.commission_recipient && amount > remaining + 0.01) {
		frm.set_df_property("amount_to_pay", "description",
			`<b style="color:var(--red-600);">${__("Warning: Exceeds remaining due of {0}", [format_currency(remaining)])}</b>`
		);
	} else {
		frm.set_df_property("amount_to_pay", "description", "");
	}
}

function format_currency(value) {
	return frappe.format(value || 0, { fieldtype: "Currency" });
}

function fetch_account_balance(frm) {
	if (!frm.doc.paying_account) {
		frm.set_value("account_balance", 0);
		return;
	}
	frappe.call({
		method: "nbs_customization.nbs_customization.doctype.commission_payout.commission_payout.get_account_balance",
		args: {
			account: frm.doc.paying_account,
			date: frm.doc.payout_date || frappe.datetime.get_today(),
		},
		callback(r) {
			if (r.message !== undefined) {
				frm.set_value("account_balance", r.message);
				if (frm.doc.amount_to_pay && r.message < frm.doc.amount_to_pay) {
					frappe.show_alert(
						{
							message: __(
								`Warning: Account balance ` +
								`(${frappe.format_value(r.message, { fieldtype: "Currency" })}) ` +
								`is less than Amount to Pay ` +
								`(${frappe.format_value(frm.doc.amount_to_pay, { fieldtype: "Currency" })}).`,
							),
							indicator: "orange",
						},
						6,
					);
				}
			}
		},
	});
}

function badge(value, color) {
	return `
		<span style="
			display:inline-block;
			padding:3px 8px;
			border-radius:12px;
			font-size:12px;
			font-weight:600;
			background:${color}15;
			color:${color};
		">
			${value}
		</span>
	`;
}

function get_remaining_color(remaining, allocated) {
	if (!allocated || allocated <= 0) {
		return "#6b7280"; // gray fallback
	}

	// Overpaid → still treat as critical
	if (remaining < 0) {
		return "#ef4444"; // red
	}

	if (remaining === 0) {
		return "#10b981"; // green → nothing left
	}

	const ratio = remaining / allocated;

	// Mostly unpaid
	if (ratio > 0.5) {
		return "#ef4444"; // red
	}

	// Partially remaining
	return "#f59e0b"; // orange
}

function get_paid_color(paid, allocated) {
	if (!allocated || allocated <= 0) {
		return "#6b7280"; // gray fallback
	}

	if (paid < 0 || paid > allocated) {
		return "#ef4444"; // red → invalid / overpaid
	}

	if (paid === 0) {
		return "#ef4444"; // red → nothing paid
	}

	if (paid === allocated) {
		return "#10b981"; // green → fully paid
	}

	const ratio = paid / allocated;

	// Less than half paid
	if (ratio < 0.5) {
		return "#ef4444"; // red
	}

	// Partial progress
	return "#f59e0b"; // orange
}