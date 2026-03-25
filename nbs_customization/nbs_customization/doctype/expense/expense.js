// Copyright (c) 2024, NBS Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Expense", {
	setup(frm) {
		frm.set_query("paying_account", function () {
			return {
				filters: {
					account_type: ["in", ["Cash", "Bank"]],
					company: frm.doc.company || frappe.defaults.get_user_default("Company"),
					is_group: 0,
				},
			};
		});

		frm.set_query("cost_center", function () {
			return {
				filters: {
					company: frm.doc.company || frappe.defaults.get_user_default("Company"),
					is_group: 0,
				},
			};
		});

		frm.set_query("purchase_invoice", function () {
			return {
				filters: {
					docstatus: 1,
					company: frm.doc.company || frappe.defaults.get_user_default("Company"),
					status: ["not in", ["Paid", "Cancelled"]],
				},
			};
		});

		frm.set_query("linked_purchase", function () {
			return {
				filters: {
					docstatus: 1,
					company: frm.doc.company || frappe.defaults.get_user_default("Company"),
				},
			};
		});
	},

	refresh(frm) {
		toggle_accompanying_fields(frm);
		toggle_payment_fields(frm);
		toggle_lcv_button(frm);
	},

	// ------------------------------------------------------------------ //
	// Field events                                                         //
	// ------------------------------------------------------------------ //

	company(frm) {
		// Refresh account filters when company changes
		frm.set_value("paying_account", null);
		frm.set_value("cost_center", null);
		frm.set_value("purchase_invoice", null);
		frm.refresh_fields(["paying_account", "cost_center", "purchase_invoice"]);
	},

	payment_type(frm) {
		toggle_payment_fields(frm);
		// Clear invoice link if switching back to direct
		if (frm.doc.payment_type === "Direct Payment") {
			frm.set_value("purchase_invoice", null);
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
					// Pre-fill amount from outstanding
					frm.set_value("amount", pi.outstanding_amount);
					// Pre-fill payee from supplier
					if (!frm.doc.payee) {
						frm.set_value("payee", pi.supplier);
					}
					// Show outstanding amount info
					frappe.show_alert(
						{
							message: __(
								`Outstanding: ${frappe.format_value(pi.outstanding_amount, {
									fieldtype: "Currency",
								})}`,
							),
							indicator: "blue",
						},
						5,
					);
				}
			},
		});
	},

	paying_account(frm) {
		fetch_account_balance(frm);
	},

	expense_date(frm) {
		fetch_account_balance(frm);
	},

	is_accompanying(frm) {
		toggle_accompanying_fields(frm);
		if (!frm.doc.is_accompanying) {
			frm.set_value("linked_purchase", null);
			frm.set_value("landed_cost_voucher", null);
		}
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
});

// ------------------------------------------------------------------ //
// Helpers                                                             //
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

function toggle_payment_fields(frm) {
	const is_invoice = frm.doc.payment_type === "Against Purchase Invoice";
	frm.set_df_property("purchase_invoice", "hidden", is_invoice ? 0 : 1);
	frm.set_df_property("purchase_invoice", "reqd", is_invoice ? 1 : 0);
	frm.refresh_fields(["purchase_invoice"]);
}

function toggle_accompanying_fields(frm) {
	const show = frm.doc.is_accompanying ? 1 : 0;
	frm.set_df_property("linked_purchase", "hidden", show ? 0 : 1);
	frm.set_df_property("linked_purchase", "reqd", show);
	frm.refresh_fields(["linked_purchase"]);
}

function toggle_lcv_button(frm) {
	frm.remove_custom_button(__("Make Landed Cost Voucher"), __("Create"));
	frm.remove_custom_button(__("View Landed Cost Voucher"), __("View"));

	const is_submitted = frm.doc.docstatus === 1;
	const is_accompanying = frm.doc.is_accompanying;
	const has_purchase = !!frm.doc.linked_purchase;
	const lcv_not_created = !frm.doc.landed_cost_voucher;

	if (is_submitted && is_accompanying && has_purchase && lcv_not_created) {
		frm.add_custom_button(
			__("Landed Cost Voucher"),
			function () {
				frappe.confirm(
					__(`Create a Landed Cost Voucher for <b>${frm.doc.name}</b>?<br>
                    After creation, click <b>Get Items</b> on the LCV, then 
                    set per-item distribution amounts before submitting.`),
					function () {
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
												`LCV ${r.message} created. Click Get Items, ` +
													`adjust distribution, then submit.`,
											),
											indicator: "green",
										},
										7,
									);
									frappe.set_route("Form", "Landed Cost Voucher", r.message);
								}
							},
						});
					},
				);
			},
			__("Create"),
		);
	}

	if (is_submitted && is_accompanying && frm.doc.landed_cost_voucher) {
		frm.add_custom_button(
			__("View Landed Cost Voucher"),
			function () {
				frappe.set_route("Form", "Landed Cost Voucher", frm.doc.landed_cost_voucher);
			},
			__("View"),
		);
	}

	// Show Payment Entry link if Flow B
	if (is_submitted && frm.doc.payment_entry) {
		frm.add_custom_button(
			__("View Payment Entry"),
			function () {
				frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
			},
			__("View"),
		);
	}
}
