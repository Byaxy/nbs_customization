// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

// ─────────────────────────────────────────────────────────────────────────────
//  Commission Payout Form
// ─────────────────────────────────────────────────────────────────────────────
frappe.ui.form.on("Commission Payout", {
	// ── Setup: static filters ────────────────────────────────────────────────

	setup(frm) {
		// Restrict paying_account to leaf (non-group), non-disabled accounts
		frm.set_query("paying_account", function () {
			return {
				filters: {
					is_group: 0,
					disabled: 0,
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
		_render_recipient_info_panel(frm);

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

	// ── Commission selected ──────────────────────────────────────────────────

	commission(frm) {
		// Clear dependent fields
		frm.set_value("commission_recipient", "");
		frm.set_value("sales_person", "");
		_clear_recipient_info_panel(frm);

		if (!frm.doc.commission) {
			_reset_recipient_filter(frm);
			return;
		}

		// Apply dynamic filter: only unpaid/partial recipients of this commission
		_apply_recipient_filter(frm);
	},

	// ── Recipient selected ───────────────────────────────────────────────────

	commission_recipient(frm) {
		if (!frm.doc.commission_recipient) {
			_clear_recipient_info_panel(frm);
			frm.set_value("amount_to_pay", 0);
			return;
		}

		_load_recipient_details(frm);
	},

	// ── Amount validation (live) ─────────────────────────────────────────────

	amount_to_pay(frm) {
		_validate_amount_live(frm);
	},

	// ── Before submit: final client-side gate ────────────────────────────────

	before_submit(frm) {
		return new Promise((resolve, reject) => {
			const amount = frm.doc.amount_to_pay || 0;
			const remaining = frm._recipient_remaining_due || null;

			if (amount <= 0) {
				frappe.msgprint({
					title: __("Invalid Amount"),
					message: __("Amount To Pay must be greater than zero."),
					indicator: "red",
				});
				return reject();
			}

			if (remaining !== null && amount > remaining + 0.01) {
				frappe.msgprint({
					title: __("Amount Exceeds Remaining Due"),
					message: __(
						"Amount To Pay ({0}) exceeds the Remaining Due ({1}) for this recipient.",
						[format_currency(amount), format_currency(remaining)],
					),
					indicator: "red",
				});
				return reject();
			}

			resolve();
		});
	},
});

// ─────────────────────────────────────────────────────────────────────────────
//  Private helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Apply a dynamic get_query filter on commission_recipient so the link field
 * only shows recipients from the selected commission that are not fully paid.
 * We store the eligible names from the server and use them as an "in" filter.
 */
function _apply_recipient_filter(frm) {
	const commission = frm.doc.commission;
	if (!commission) {
		_reset_recipient_filter(frm);
		return;
	}

	frappe.call({
		method: "nbs_customization.nbs_customization.doctype.sales_commission.sales_commission.get_recipients_for_commission",
		args: { commission: commission },
		callback(r) {
			const recipients = r.message || [];
			// Cache on frm for later use in UI
			frm._eligible_recipients = recipients;

			if (recipients.length === 0) {
				frappe.msgprint({
					title: __("No Eligible Recipients"),
					message: __("All recipients for Commission <b>{0}</b> have been fully paid.", [
						commission,
					]),
					indicator: "orange",
				});
				_reset_recipient_filter(frm);
				return;
			}

			const eligible_names = recipients.map((r) => r.name);

			frm.set_query("commission_recipient", function () {
				return {
					filters: {
						name: ["in", eligible_names],
					},
				};
			});
		},
	});
}

function _reset_recipient_filter(frm) {
	frm._eligible_recipients = [];
	frm._recipient_remaining_due = null;
	frm.set_query("commission_recipient", function () {
		// Show nothing if no commission selected
		return { filters: { name: "__nonexistent__" } };
	});
}

/**
 * After a recipient is selected, load their payment details and:
 * - Show an informational panel (allocated / paid / remaining)
 * - Pre-fill amount_to_pay with the full remaining_due
 */
function _load_recipient_details(frm) {
	const recipient_name = frm.doc.commission_recipient;
	const cached = (frm._eligible_recipients || []).find((r) => r.name === recipient_name);

	if (cached) {
		_render_recipient_details(frm, cached);
		return;
	}

	// Fallback: fetch directly (e.g. when editing an existing payout)
	frappe.db.get_value(
		"Commission Recipient",
		recipient_name,
		["sales_person", "allocated_amount", "paid_amount", "remaining_due", "payment_status"],
		(r) => {
			if (r) _render_recipient_details(frm, r);
		},
	);
}

function _render_recipient_details(frm, data) {
	const allocated = data.allocated_amount || 0;
	const paid = data.paid_amount || 0;
	const remaining =
		data.remaining_due !== undefined ? data.remaining_due : Math.max(0, allocated - paid);

	// Cache remaining_due for before_submit validation
	frm._recipient_remaining_due = remaining;

	// Pre-fill amount with remaining due
	if (frm.doc.docstatus === 0) {
		frm.set_value("amount_to_pay", parseFloat(remaining.toFixed(2)));
	}

	_render_recipient_info_panel(frm, {
		allocated_amount: allocated,
		paid_amount: paid,
		remaining_due: remaining,
		payment_status: data.payment_status || "Pending",
	});
}

function _render_recipient_info_panel(frm, data) {
	// Remove any existing info panel
	frm.fields_dict.notes &&
		$(frm.fields_dict.notes.wrapper).find(".recipient-info-panel").remove();

	if (!data || !frm.doc.commission_recipient) return;

	const status_color =
		{
			Pending: "#f0ad4e",
			Partial: "#5b9bd5",
			Paid: "#28a745",
			Cancelled: "#dc3545",
		}[data.payment_status] || "#888";

	const html = `
        <div class="recipient-info-panel" style="
            background: var(--bg-color, #f9f9f9);
            border: 1px solid var(--border-color, #d1d8dd);
            border-left: 4px solid ${status_color};
            border-radius: 4px;
            padding: 12px 16px;
            margin: 8px 0 12px 0;
            font-size: 13px;
        ">
            <div style="display:flex; gap:32px; flex-wrap:wrap;">
                <div>
                    <div style="color:var(--text-muted); font-size:11px; margin-bottom:2px;">${__("Allocated")}</div>
                    <div style="font-weight:600;">${format_currency(data.allocated_amount)}</div>
                </div>
                <div>
                    <div style="color:var(--text-muted); font-size:11px; margin-bottom:2px;">${__("Paid So Far")}</div>
                    <div style="font-weight:600; color:${data.paid_amount > 0 ? "#28a745" : "inherit"};">${format_currency(data.paid_amount)}</div>
                </div>
                <div>
                    <div style="color:var(--text-muted); font-size:11px; margin-bottom:2px;">${__("Remaining Due")}</div>
                    <div style="font-weight:700; color:${data.remaining_due > 0 ? "#e86325" : "#28a745"};">${format_currency(data.remaining_due)}</div>
                </div>
                <div>
                    <div style="color:var(--text-muted); font-size:11px; margin-bottom:2px;">${__("Status")}</div>
                    <div style="font-weight:600; color:${status_color};">${__(data.payment_status)}</div>
                </div>
            </div>
        </div>
    `;

	// Insert the panel above the notes field
	if (frm.fields_dict.notes) {
		$(frm.fields_dict.notes.wrapper).prepend(html);
	} else if (frm.fields_dict.amount_to_pay) {
		$(frm.fields_dict.amount_to_pay.wrapper).after(html);
	}
}

function _clear_recipient_info_panel(frm) {
	frm._recipient_remaining_due = null;
	$(".recipient-info-panel").remove();
}

/**
 * Live validation: show a red hint if the amount exceeds remaining due.
 */
function _validate_amount_live(frm) {
	const amount = frm.doc.amount_to_pay || 0;
	const remaining = frm._recipient_remaining_due;

	if (remaining === null || remaining === undefined) return;

	const field = frm.get_field("amount_to_pay");
	if (!field) return;

	if (amount > remaining + 0.01) {
		field.set_invalid(__("Exceeds remaining due of {0}", [format_currency(remaining)]));
	} else {
		field.set_invalid("");
	}
}

function format_currency(value) {
	return frappe.format(value || 0, { fieldtype: "Currency" });
}
