// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Expense", {
	// ------------------------------------------------------------------ //
	// Form lifecycle                                                       //
	// ------------------------------------------------------------------ //

	setup(frm) {
		// Filter paying account to Cash and Bank accounts only
		frm.set_query("paying_account", function () {
			return {
				filters: {
					account_type: ["in", ["Cash", "Bank"]],
					company: frappe.defaults.get_user_default("Company"),
					is_group: 0,
				},
			};
		});

		// Filter linked_purchase to submitted Purchase Receipts only
		frm.set_query("linked_purchase", function () {
			return {
				filters: {
					docstatus: 1,
					company: frappe.defaults.get_user_default("Company"),
				},
			};
		});
	},

	refresh(frm) {
		toggle_accompanying_fields(frm);
		toggle_lcv_button(frm);
	},

	// ------------------------------------------------------------------ //
	// Field events                                                         //
	// ------------------------------------------------------------------ //

	paying_account(frm) {
		fetch_account_balance(frm);
	},

	expense_date(frm) {
		// Refresh balance when date changes — balance is date-sensitive
		fetch_account_balance(frm);
	},

	is_accompanying(frm) {
		toggle_accompanying_fields(frm);
		if (!frm.doc.is_accompanying) {
			frm.set_value("linked_purchase", null);
			frm.set_value("accompanying_type", null);
			frm.set_value("landed_cost_voucher", null);
		}
	},

	linked_purchase(frm) {
		if (!frm.doc.linked_purchase || !frm.doc.company) return;

		// Validate the selected Purchase Receipt belongs to the same company
		frappe.db.get_value("Purchase Receipt", frm.doc.linked_purchase, "company", (r) => {
			const company = frappe.defaults.get_user_default("Company");
			if (r && r.company !== company) {
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

				// Warn inline if balance is less than amount already entered
				if (frm.doc.amount && r.message < frm.doc.amount) {
					frappe.show_alert(
						{
							message: __(
								`Warning: Account balance 
							(${format_currency(r.message)}) 
							is less than expense amount 
							(${format_currency(frm.doc.amount)}).`,
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

function format_currency(value) {
	return frappe.format_value(value, { fieldtype: "Currency" });
}

function toggle_accompanying_fields(frm) {
	const show = frm.doc.is_accompanying ? 1 : 0;
	frm.set_df_property("linked_purchase", "hidden", show ? 0 : 1);
	frm.set_df_property("accompanying_type", "hidden", show ? 0 : 1);
	frm.set_df_property("linked_purchase", "reqd", show);
	frm.set_df_property("accompanying_type", "reqd", show);
	frm.refresh_fields(["linked_purchase", "accompanying_type"]);
}

function toggle_lcv_button(frm) {
	frm.remove_custom_button(__("Make Landed Cost Voucher"), __("Create"));

	const is_submitted = frm.doc.docstatus === 1;
	const is_accompanying = frm.doc.is_accompanying;
	const has_purchase = !!frm.doc.linked_purchase;
	const lcv_not_created = !frm.doc.landed_cost_voucher;

	if (is_submitted && is_accompanying && has_purchase && lcv_not_created) {
		frm.add_custom_button(
			__("Landed Cost Voucher"),
			function () {
				frappe.confirm(
					__(`Create a Landed Cost Voucher for 
					<b>${frm.doc.name}</b>? 
					You will need to click 
					<b>Get Items</b> on the LCV before submitting.`),
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
												`Landed Cost Voucher ${r.message} created. Click Get Items before submitting.`,
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

	// If LCV exists — show a link button to open it directly
	if (is_submitted && is_accompanying && frm.doc.landed_cost_voucher) {
		frm.add_custom_button(
			__("View Landed Cost Voucher"),
			function () {
				frappe.set_route("Form", "Landed Cost Voucher", frm.doc.landed_cost_voucher);
			},
			__("View"),
		);
	}
}
