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
			}
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
			__("View")
		);
	} else {
		frm.add_custom_button(
			__("Receipt"),
			() =>
				frappe.model.open_mapped_doc({
					method: "nbs_customization.nbs_customization.doctype.receipt.receipt.create_receipt_from_pe",
					frm: frm,
				}),
			__("Create")
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
					"Mark this cheque as returned/bounced? This reverses any clearing and cancels the Payment Entry, re-opening the allocated invoices."
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
										[frm.doc.name]
									)
								);
								frm.reload_doc();
							}
						},
					});
				}
			);
		},
		__("Cheque")
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
							])
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

const REFERENCE_MANDATORY =
	"eval:doc.is_check==1 || doc.paid_from_account_type == 'Bank' || doc.paid_to_account_type == 'Bank'";

function ensure_reference_mandatory_rule(frm) {
	// Core re-evaluates mandatory_depends_on on every layout refresh and
	// overwrites a plain `reqd` flag, so extend the rule to cover cheque mode.
	for (const fieldname of ["reference_no", "reference_date"]) {
		const field = frm.get_field(fieldname);
		if (field && field.df.mandatory_depends_on !== REFERENCE_MANDATORY) {
			frm.set_df_property(fieldname, "mandatory_depends_on", REFERENCE_MANDATORY);
		}
	}
}

function toggle_check_reference_required(frm) {
	ensure_reference_mandatory_rule(frm);
	const apply = (is_check) => {
		if (!!frm.doc.is_check !== !!is_check) frm.set_value("is_check", is_check ? 1 : 0);
		frm.set_df_property("reference_no", "reqd", is_check);
		frm.set_df_property("reference_date", "reqd", is_check);
		frm.set_df_property("check_bank", "reqd", is_check);
		frm.toggle_display("check_bank", is_check);
	};
	if (!frm.doc.mode_of_payment) {
		apply(false);
		return;
	}
	// Apply from the saved flag first so load/amend show the right state
	// without waiting for the async lookup below.
	apply(!!frm.doc.is_check);
	const requested_mode = frm.doc.mode_of_payment;
	frappe.db.get_value("Mode of Payment", frm.doc.mode_of_payment, "is_check", (r) => {
		// guard stale callback if user quickly switched modes
		if (frm.doc.mode_of_payment !== requested_mode) return;
		apply(!!(r && r.is_check));
	});
}

frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		maybe_add_receipt_button(frm);
		add_check_clearing_buttons(frm);
		toggle_check_reference_required(frm);
	},
	mode_of_payment(frm) {
		toggle_check_reference_required(frm);
	},
	validate(frm) {
		if (frm.doc.is_check) {
			if (!frm.doc.reference_no || !frm.doc.reference_date) {
				frappe.msgprint(
					__("Cheque/Reference No and Reference Date are mandatory for Check payments.")
				);
				frappe.validated = false;
			}
			if (!frm.doc.check_bank) {
				frappe.msgprint(__("Check Bank is mandatory for Check payments."));
				frappe.validated = false;
			}
		}
	},
});
