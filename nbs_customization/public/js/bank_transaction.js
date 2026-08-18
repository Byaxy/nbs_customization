// Copyright (c) 2026, NBS Solutions and contributors
// For license information, please see license.txt

function clear_cheque_dialog(frm) {
	frappe.call({
		method: "nbs_customization.controllers.bank_transaction.get_uncleared_check_candidates",
		args: { bank_transaction_name: frm.doc.name },
		callback(r) {
			if (!r.message || !r.message.length) {
				frappe.msgprint(__("No matching uncleared cheque Payment Entries found."));
				return;
			}

			let options = r.message.map((c) => ({
				value: c.name,
				label:
					`${c.name} \u00b7 ${c.party} \u00b7 ${c.paid_amount.toLocaleString()} ` +
					`${frm.doc.currency || ""} \u00b7 ${c.reference_no || __("no ref")} \u00b7 ${c.posting_date}`,
			}));

			let d = new frappe.ui.Dialog({
				title: __("Clear Cheque against Bank Transaction"),
				fields: [
					{
						fieldtype: "Select",
						fieldname: "payment_entry",
						label: __("Cheque Payment Entry"),
						options: options,
						reqd: 1,
					},
				],
				primary_action_label: __("Clear & Reconcile"),
				primary_action(values) {
					frappe.call({
						method: "nbs_customization.controllers.bank_transaction.clear_check_from_bank_transaction",
						args: {
							bank_transaction_name: frm.doc.name,
							payment_entry_name: values.payment_entry,
						},
						freeze: true,
						freeze_message: __("Clearing cheque and reconciling..."),
						callback(cb) {
							if (!cb.exc) {
								frappe.msgprint(
									__(
										"Cheque cleared and Bank Transaction reconciled. Journal Entry {0} linked.",
										[cb.message.journal_entry],
									),
								);
								d.hide();
								frm.reload_doc();
							}
						},
					});
				},
			});
			d.show();
		},
	});
}

frappe.ui.form.on("Bank Transaction", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 1 || Number(frm.doc.unallocated_amount) <= 0)
			return;
		frm.add_custom_button(__("Clear Cheque"), () => clear_cheque_dialog(frm), __("Cheque"));
	},
});
