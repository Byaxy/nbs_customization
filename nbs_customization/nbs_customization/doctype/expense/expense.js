// Copyright (c) 2024, NBS Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Expense", {
	setup(frm) {
		frm.set_query("paying_account", () => ({
			filters: {
				account_type: ["in", ["Cash", "Bank"]],
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
				is_group: 0,
			},
		}));
		frm.set_query("cost_center", () => ({
			filters: {
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
				is_group: 0,
			},
		}));
		frm.set_query("purchase_invoice", () => ({
			filters: {
				docstatus: 1,
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
				status: ["not in", ["Paid", "Cancelled"]],
			},
		}));
		frm.set_query("linked_purchase", () => ({
			filters: {
				docstatus: 1,
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
			},
		}));
		frm.set_query("linked_shipment", () => ({
			query: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_shipments_search",
			filters: {
				company: frm.doc.company || frappe.defaults.get_user_default("Company"),
			},
		}));
	},

	refresh(frm) {
		toggle_accompanying_fields(frm);
		toggle_payment_fields(frm);
		toggle_lcv_button(frm);
	},

	// ---------------------------------------------------------------- //
	// Field events                                                       //
	// ---------------------------------------------------------------- //

	company(frm) {
		frm.set_value("paying_account", null);
		frm.set_value("cost_center", null);
		frm.set_value("purchase_invoice", null);
		frm.set_value("linked_shipment", null);
		frm.refresh_fields([
			"paying_account",
			"cost_center",
			"purchase_invoice",
			"linked_shipment",
		]);
	},

	payment_type(frm) {
		toggle_payment_fields(frm);
		if (frm.doc.payment_type === "Direct Payment") {
			frm.set_value("purchase_invoice", null);
		}
	},

	is_accompanying(frm) {
		toggle_accompanying_fields(frm);
		if (!frm.doc.is_accompanying) {
			frm.set_value("expense_scope", null);
			frm.set_value("linked_purchase", null);
			frm.set_value("linked_shipment", null);
			frm.set_value("landed_cost_voucher", null);
		}
	},

	expense_scope(frm) {
		toggle_accompanying_fields(frm);
		// Clear the unused link when switching scope
		if (frm.doc.expense_scope === "Single Purchase Receipt") {
			frm.set_value("linked_shipment", null);
		} else if (frm.doc.expense_scope === "Inbound Shipment") {
			frm.set_value("linked_purchase", null);
		}
	},

	purchase_invoice(frm) {
		if (!frm.doc.purchase_invoice) return;
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.expense.expense.get_invoice_details",
			args: { purchase_invoice: frm.doc.purchase_invoice },
			callback(r) {
				if (r.message) {
					const pi = r.message;
					frm.set_value("amount", pi.outstanding_amount);
					if (!frm.doc.payee) frm.set_value("payee", pi.supplier);
					frappe.show_alert(
						{
							message: __(
								`Outstanding: ${frappe.format_value(pi.outstanding_amount, { fieldtype: "Currency" })}`,
							),
							indicator: "blue",
						},
						5,
					);
				}
			},
		});
	},

	linked_purchase(frm) {
		if (!frm.doc.linked_purchase || !frm.doc.company) return;
		frappe.db.get_value("Purchase Receipt", frm.doc.linked_purchase, "company", (r) => {
			if (r && r.company !== frm.doc.company) {
				frappe.msgprint(
					__("The selected Purchase Receipt belongs to a different company."),
				);
				frm.set_value("linked_purchase", null);
			}
		});
	},

	linked_shipment(frm) {
		if (!frm.doc.linked_shipment) {
			clear_shipment_info_panel(frm);
			return;
		}
		fetch_shipment_info(frm);
	},

	paying_account(frm) {
		fetch_account_balance(frm);
	},
	expense_date(frm) {
		fetch_account_balance(frm);
	},
});

// ------------------------------------------------------------------ //
// Field visibility helpers                                             //
// ------------------------------------------------------------------ //

function toggle_payment_fields(frm) {
	const is_invoice = frm.doc.payment_type === "Against Purchase Invoice";
	frm.set_df_property("purchase_invoice", "hidden", is_invoice ? 0 : 1);
	frm.set_df_property("purchase_invoice", "reqd", is_invoice ? 1 : 0);
	frm.refresh_fields(["purchase_invoice"]);
}

function toggle_accompanying_fields(frm) {
	const show = frm.doc.is_accompanying ? 1 : 0;
	const scope = frm.doc.expense_scope || "Single Purchase Receipt";
	const is_single = scope === "Single Purchase Receipt";
	const is_shipment = scope === "Inbound Shipment";

	// Scope selector only when accompanying
	frm.set_df_property("expense_scope", "hidden", show ? 0 : 1);

	// Single PR fields
	frm.set_df_property("linked_purchase", "hidden", show && is_single ? 0 : 1);
	frm.set_df_property("linked_purchase", "reqd", show && is_single ? 1 : 0);

	// Shipment fields
	frm.set_df_property("linked_shipment", "hidden", show && is_shipment ? 0 : 1);
	frm.set_df_property("linked_shipment", "reqd", show && is_shipment ? 1 : 0);

	frm.refresh_fields(["expense_scope", "linked_purchase", "linked_shipment"]);

	// Clear the info panel if not shipment scope
	if (!show || !is_shipment) {
		clear_shipment_info_panel(frm);
	}
}

// ------------------------------------------------------------------ //
// Shipment info panel                                                  //
// ------------------------------------------------------------------ //

function fetch_shipment_info(frm) {
	frappe.call({
		method: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_shipment_summary",
		args: { shipment_name: frm.doc.linked_shipment },
		callback(r) {
			if (r.message) render_shipment_info_panel(frm, r.message);
		},
	});
}

function render_shipment_info_panel(frm, s) {
	// Find or create a notification area below the linked_shipment field
	const $field = frm.get_field("linked_shipment").$wrapper;
	$field.find(".shipment-info-panel").remove();
	$field.append(`
        <div class="shipment-info-panel alert alert-info mt-2 mb-0" style="font-size:12px;">
            <strong>${frm.doc.linked_shipment}</strong> — 
            ${s.shipping_mode} | ${s.carrier} | 
            ${s.pr_count} Purchase Receipt(s) | 
            ${flt(s.total_chargeable_weight, 2)} kg chargeable |
            Status: <b>${s.status}</b>
        </div>
    `);
}

function clear_shipment_info_panel(frm) {
	const field = frm.get_field("linked_shipment");
	if (field) field.$wrapper.find(".shipment-info-panel").remove();
}

// ------------------------------------------------------------------ //
// Account balance                                                      //
// ------------------------------------------------------------------ //

function fetch_account_balance(frm) {
	if (!frm.doc.paying_account) {
		frm.set_value("account_balance", 0);
		return;
	}
	frappe.call({
		method: "nbs_customization.nbs_customization.doctype.expense.expense.get_account_balance",
		args: {
			account: frm.doc.paying_account,
			date: frm.doc.expense_date || frappe.datetime.get_today(),
		},
		callback(r) {
			if (r.message !== undefined) {
				frm.set_value("account_balance", r.message);
				if (frm.doc.amount && r.message < frm.doc.amount) {
					frappe.show_alert(
						{
							message: __(
								`Warning: Account balance ` +
									`(${frappe.format_value(r.message, { fieldtype: "Currency" })}) ` +
									`is less than expense amount ` +
									`(${frappe.format_value(frm.doc.amount, { fieldtype: "Currency" })}).`,
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

// ------------------------------------------------------------------ //
// Custom action buttons                                                //
// ------------------------------------------------------------------ //

function toggle_lcv_button(frm) {
	frm.remove_custom_button(__("Make Landed Cost Voucher"), __("Create"));
	frm.remove_custom_button(__("View Landed Cost Voucher"), __("View"));
	frm.remove_custom_button(__("View Inbound Shipment"), __("View"));
	frm.remove_custom_button(__("View Payment Entry"), __("View"));

	const submitted = frm.doc.docstatus === 1;
	const is_acc = frm.doc.is_accompanying;
	const lcv_not_made = !frm.doc.landed_cost_voucher;
	const scope = frm.doc.expense_scope || "Single Purchase Receipt";
	const has_pr = scope === "Single Purchase Receipt" && !!frm.doc.linked_purchase;
	const has_ship = scope === "Inbound Shipment" && !!frm.doc.linked_shipment;

	// "Make LCV" button — available when no LCV yet
	if (submitted && is_acc && lcv_not_made && (has_pr || has_ship)) {
		const scope_label = has_ship
			? `Inbound Shipment <b>${frm.doc.linked_shipment}</b>`
			: `Purchase Receipt <b>${frm.doc.linked_purchase}</b>`;

		frm.add_custom_button(
			__("Landed Cost Voucher"),
			function () {
				// For shipment scope — pre-flight receiving check before confirm
				if (has_ship) {
					frappe.call({
						method: "nbs_customization.nbs_customization.doctype.expense.expense.check_shipment_fully_received",
						args: { shipment_name: frm.doc.linked_shipment },
						freeze: true,
						freeze_message: __("Checking receiving status..."),
						callback(r) {
							if (!r.message) return;

							if (!r.message.ready) {
								// Show the detailed breakdown — don't proceed
								frappe.msgprint({
									title: __("Shipment Not Fully Received"),
									message: r.message.message,
									indicator: "orange",
								});
								return;
							}
							// All items received — proceed to confirm
							confirm_and_create_lcv(frm, scope_label);
						},
					});
				} else {
					// Single PR scope — no receiving check needed
					confirm_and_create_lcv(frm, scope_label);
				}
			},
			__("Create"),
		);
	}

	// View LCV
	if (submitted && is_acc && frm.doc.landed_cost_voucher) {
		frm.add_custom_button(
			__("View Landed Cost Voucher"),
			() => {
				frappe.set_route("Form", "Landed Cost Voucher", frm.doc.landed_cost_voucher);
			},
			__("View"),
		);
	}

	// View Inbound Shipment
	if (frm.doc.linked_shipment) {
		frm.add_custom_button(
			__("View Inbound Shipment"),
			() => {
				frappe.set_route("Form", "Inbound Shipment", frm.doc.linked_shipment);
			},
			__("View"),
		);
	}

	// View Payment Entry (Flow B)
	if (submitted && frm.doc.payment_entry) {
		frm.add_custom_button(
			__("View Payment Entry"),
			() => {
				frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
			},
			__("View"),
		);
	}
}

function confirm_and_create_lcv(frm, scope_label) {
	frappe.confirm(
		__(`Create a Landed Cost Voucher for <b>${frm.doc.name}</b>?<br>
            Scope: ${scope_label}<br><br>
            After creation, click <b>Get Items</b> on the LCV, then
            use the <b>Distribution Calculator</b> (By Weight) before submitting.`),
		() => {
			frappe.call({
				method: "nbs_customization.nbs_customization.doctype.expense.expense.make_landed_cost_voucher",
				args: { expense_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating Landed Cost Voucher..."),
				callback(r) {
					if (r.message) {
						frm.reload_doc();
						frappe.show_alert(
							{
								message: __(
									`LCV <b>${r.message}</b> created. ` +
										`Click Get Items, run the Distribution Calculator (By Weight), then submit.`,
								),
								indicator: "green",
							},
							8,
						);
						frappe.set_route("Form", "Landed Cost Voucher", r.message);
					}
				},
			});
		},
	);
}
