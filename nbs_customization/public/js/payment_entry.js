// Copyright (c) 2026, NBS Solutions and contributors
// For license information, please see license.txt

frappe.provide("erpnext.accounts.pos");

// Route cheque modes of payment to the direction-correct clearing account when
// the base code fetches the mode's payment account (the stock account pickers
// cannot list clearing accounts, which have no Bank/Cash account type).
(function () {
	let pos_account_getter = erpnext.accounts.pos.get_payment_mode_account;

	erpnext.accounts.pos.get_payment_mode_account = function (frm, mode_of_payment, callback) {
		if (!mode_of_payment) {
			if (pos_account_getter) return pos_account_getter(frm, mode_of_payment, callback);
			return null;
		}
		frappe.db.get_value(
			"Mode of Payment",
			mode_of_payment,
			["is_check", "clearing_account_inward", "clearing_account_outward"],
			(r) => {
				let account = "";
				if (r && r.is_check) {
					account =
						frm.doc.payment_type === "Receive"
							? r.clearing_account_inward
							: r.clearing_account_outward;
				}
				if (account) {
					callback(account);
				} else if (pos_account_getter) {
					pos_account_getter(frm, mode_of_payment, callback);
				}
			},
		);
	};
})();

function maybe_add_receipt_button(frm) {
	if (
		frm.doc.docstatus !== 1 ||
		frm.doc.payment_type !== "Receive" ||
		frm.doc.party_type !== "Customer"
	)
		return;

	if (frm.doc.custom_receipt) {
		frm.add_custom_button(
			__("Receipt"),
			() => frappe.set_route("Form", "Receipt", frm.doc.custom_receipt),
			__("View"),
		);
	} else {
		frm.add_custom_button(
			__("Receipt"),
			() =>
				frappe.model.open_mapped_doc({
					method: "nbs_customization.nbs_customization.doctype.receipt.receipt.create_receipt_from_pe",
					frm: frm,
				}),
			__("Create"),
		);
		frm.page.set_inner_btn_group_as_primary(__("Create"));
	}
}

function add_check_clearing_buttons(frm) {
	if (
		frm.doc.docstatus !== 1 ||
		!frm.doc.is_check ||
		frm.doc.check_cleared ||
		frm.doc.check_returned ||
		frm.doc.clearing_journal_entry
	)
		return;

	frm.add_custom_button(__("Mark Check Cleared"), () => clearing_dialog(frm), __("Cheque"));

	frm.add_custom_button(
		__("Mark Check Returned"),
		() => {
			frappe.confirm(
				__(
					"Mark this cheque as returned/bounced? This reverses any clearing and cancels the Payment Entry, re-opening the allocated invoices.",
				),
				() => {
					frappe.call({
						method: "nbs_customization.controllers.payment_entry.mark_check_returned",
						args: { name: frm.doc.name },
						freeze: true,
						freeze_message: __("Marking cheque as returned..."),
						callback(r) {
							if (!r.exc) {
								frappe.msgprint(
									__(
										"Payment Entry {0} cancelled. Invoice allocations are re-opened.",
										[frm.doc.name],
									),
								);
								frm.reload_doc();
							}
						},
					});
				},
			);
		},
		__("Cheque"),
	);
}

function clearing_dialog(frm) {
	let d = new frappe.ui.Dialog({
		title: __("Mark Check Cleared"),
		fields: [
			{
				fieldtype: "Link",
				fieldname: "clearing_destination_account",
				label: __("Destination Account"),
				options: "Account",
				default: frm.doc.clearing_destination_account,
				reqd: 1,
				get_query() {
					return {
						filters: {
							company: frm.doc.company,
							is_group: 0,
							account_type: ["in", ["Bank", "Cash"]],
						},
					};
				},
			},
			{
				fieldtype: "Date",
				fieldname: "clearing_date",
				label: __("Clearing Date"),
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
		],
		primary_action_label: __("Clear"),
		primary_action(values) {
			frappe.call({
				method: "nbs_customization.controllers.payment_entry.mark_check_cleared",
				args: {
					name: frm.doc.name,
					destination_account: values.clearing_destination_account,
					clearing_date: values.clearing_date,
				},
				freeze: true,
				freeze_message: __("Clearing cheque..."),
				callback(r) {
					if (!r.exc) {
						frappe.msgprint(
							__("Cheque cleared. Journal Entry {0} created.", [
								r.message.journal_entry,
							]),
						);
						d.hide();
						frm.reload_doc();
					}
				},
			});
		},
	});
	d.show();
}

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		maybe_add_receipt_button(frm);
		add_check_clearing_buttons(frm);
	},
});
