// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Receipt", {
	setup(frm) {
		_set_address_contact_filters(frm);
		_set_payment_entry_query(frm);
		_set_sales_invoice_query(frm);
	},

	refresh(frm) {
		_add_custom_buttons(frm);
		_lock_payment_methods_grid(frm);
	},

	customer(frm) {
		if (!frm.doc.customer) {
			frm.set_value("customer_name", "");
			frm.set_value("customer_address", "");
			frm.set_value("billing_address", "");
			frm.set_value("customer_address_display", "");
			frm.set_value("billing_address_display", "");
			return;
		}
		load_customer_addresses(frm);
	},

	customer_address(frm) {
		update_address_display(frm, "customer_address", "customer_address_display");
	},

	billing_address(frm) {
		update_address_display(frm, "billing_address", "billing_address_display");
	},
});

frappe.ui.form.on("Receipt Payment", {
	payment_entry(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.payment_entry) {
			_clear_payment_row(row, cdt, cdn);
			return;
		}

		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.receipt.receipt.get_payment_entry_details",
			args: { payment_entry: row.payment_entry },
			freeze: true,
			freeze_message: __("Loading Payment Entry details..."),
			callback(r) {
				if (!r.message || !r.message.rows) return;

				r.message.rows.forEach((data, i) => {
					if (i === 0) {
						frappe.model.set_value(cdt, cdn, {
							sales_invoice: data.sales_invoice || "",
							invoice_date: data.invoice_date || "",
							amount_due: data.amount_due,
							amount_received: data.amount_received,
							balance_due: data.balance_due,
							payment_method: data.payment_method || "",
							receiving_account: data.receiving_account || "",
							reference_no: data.reference_no || "",
							reference_date: data.reference_date || null,
						});
					} else {
						const child = frappe.model.add_child(
							frm.doc,
							"Receipt Payment",
							"receipt_payments",
						);
						frappe.model.set_value(child.doctype, child.name, {
							payment_entry: data.payment_entry,
							sales_invoice: data.sales_invoice || "",
							invoice_date: data.invoice_date || "",
							amount_due: data.amount_due,
							amount_received: data.amount_received,
							balance_due: data.balance_due,
							payment_method: data.payment_method || "",
							receiving_account: data.receiving_account || "",
							reference_no: data.reference_no || "",
							reference_date: data.reference_date || null,
						});
					}
				});

				frm.refresh_field("receipt_payments");
				recompute_totals(frm);
			},
		});
	},

	sales_invoice(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.sales_invoice) {
			frappe.model.set_value(cdt, cdn, "invoice_date", null);
			return;
		}
		frappe.db.get_value(
			"Sales Invoice",
			row.sales_invoice,
			["posting_date", "outstanding_amount"],
			(r) => {
				if (!r) return;
				frappe.model.set_value(cdt, cdn, "invoice_date", r.posting_date);
				if (!row.amount_due) {
					frappe.model.set_value(cdt, cdn, "amount_due", r.outstanding_amount);
				}
			},
		);
	},

	amount_received(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const balance = flt(row.amount_due) - flt(row.amount_received);
		frappe.model.set_value(cdt, cdn, "balance_due", Math.max(0, balance));
		recompute_totals(frm);
	},

	receipt_payments_remove(frm) {
		recompute_totals(frm);
	},
});

function _set_address_contact_filters(frm) {
	frm.set_query("customer_address", () => {
		if (!frm.doc.customer) return { filters: [["name", "=", ""]] };
		return {
			query: "frappe.contacts.doctype.address.address.address_query",
			filters: { link_doctype: "Customer", link_name: frm.doc.customer },
		};
	});

	frm.set_query("billing_address", () => {
		if (!frm.doc.customer) return { filters: [["name", "=", ""]] };
		return {
			query: "frappe.contacts.doctype.address.address.address_query",
			filters: { link_doctype: "Customer", link_name: frm.doc.customer },
		};
	});
}

function _set_payment_entry_query(frm) {
	frm.set_query("payment_entry", "receipt_payments", () => {
		const filters = {
			docstatus: 1,
			payment_type: "Receive",
			company: frm.doc.company,
			custom_receipt: ["is", "not set"],
		};
		if (frm.doc.customer) {
			filters.party = frm.doc.customer;
			filters.party_type = "Customer";
		}
		return { filters };
	});
}

function _set_sales_invoice_query(frm) {
	frm.set_query("sales_invoice", "receipt_payments", () => {
		if (!frm.doc.customer) return { filters: [["name", "=", ""]] };
		return {
			filters: {
				docstatus: 1,
				customer: frm.doc.customer,
				company: frm.doc.company,
				outstanding_amount: [">", 0],
			},
		};
	});
}

function _add_custom_buttons(frm) {
	if (frm.doc.docstatus === 1) {
		const linked_pe = frm.doc.receipt_payments?.map((r) => r.payment_entry).filter(Boolean);
		if (linked_pe?.length) {
			frm.add_custom_button(
				__("View Linked Payment Entries"),
				() => {
					frappe.set_route("List", "Payment Entry", {
						name: ["in", linked_pe],
					});
				},
				__("View"),
			);
		}
		return;
	}

	frm.add_custom_button(
		__("Add from Payment Entry"),
		() => show_add_from_payment_entry_dialog(frm),
		__("Get Items From"),
	);
}

function _lock_payment_methods_grid(frm) {
	const grid = frm.fields_dict.receipt_payment_methods?.grid;
	if (!grid) return;
	grid.cannot_add_rows = true;
	grid.cannot_delete_rows = true;
}

function _clear_payment_row(row, cdt, cdn) {
	frappe.model.set_value(cdt, cdn, {
		sales_invoice: "",
		invoice_date: null,
		amount_due: 0,
		amount_received: 0,
		balance_due: 0,
		payment_method: "",
		receiving_account: "",
		reference_no: "",
		reference_date: null,
	});
}

function load_customer_addresses(frm) {
	frappe.call({
		method: "frappe.contacts.doctype.address.address.get_default_address",
		args: { doctype: "Customer", name: frm.doc.customer },
		callback(r) {
			const ca = r.message;
			frm.set_value("customer_address", ca || "");
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_default_address",
				args: {
					doctype: "Customer",
					name: frm.doc.customer,
					sort_key: "is_shipping_address",
				},
				callback(r2) {
					const ba = r2.message;
					frm.set_value("billing_address", ba && ba !== ca ? ba : ca || "");
				},
			});
		},
	});
}

function update_address_display(frm, source_field, target_field) {
	if (!frm.doc[source_field]) {
		frm.set_value(target_field, "");
		return;
	}
	frappe.call({
		method: "frappe.contacts.doctype.address.address.get_address_display",
		args: { address_dict: frm.doc[source_field] },
		callback: (r) => r.message && frm.set_value(target_field, r.message),
	});
}

function recompute_totals(frm) {
	const rows = frm.doc.receipt_payments || [];
	let total_due = 0;
	let total_received = 0;
	let total_balance = 0;
	rows.forEach((r) => {
		total_due += flt(r.amount_due);
		total_received += flt(r.amount_received);
		if (r.sales_invoice) {
			total_balance += flt(r.balance_due);
		}
	});
	frm.set_value("total_amount_due", total_due);
	frm.set_value("total_amount_received", total_received);
	frm.set_value("total_balance_due", total_balance);
}

function show_add_from_payment_entry_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add from Payment Entry"),
		fields: [
			{
				fieldname: "payment_entry",
				fieldtype: "Link",
				label: "Payment Entry",
				options: "Payment Entry",
				reqd: 1,
				get_query: () => ({
					filters: {
						docstatus: 1,
						payment_type: "Receive",
						company: frm.doc.company,
						...(frm.doc.customer
							? { party: frm.doc.customer, party_type: "Customer" }
							: {}),
					},
				}),
			},
			{
				fieldname: "section_break_info",
				fieldtype: "Section Break",
			},
			{
				fieldname: "preview",
				fieldtype: "HTML",
			},
		],
		primary_action_label: __("Add to Receipt"),
		primary_action(values) {
			const pe = values.payment_entry;
			if (!pe) return;

			frappe.call({
				method: "nbs_customization.nbs_customization.doctype.receipt.receipt.get_payment_entry_details",
				args: { payment_entry: pe },
				freeze: true,
				freeze_message: __("Loading Payment Entry details..."),
				callback(r) {
					if (!r.message || !r.message.rows) return;

					const existing = new Set(
						(frm.doc.receipt_payments || []).map(
							(x) => `${x.payment_entry}::${x.sales_invoice || ""}`,
						),
					);
					let added = 0;

					r.message.rows.forEach((data) => {
						const key = `${data.payment_entry}::${data.sales_invoice || ""}`;
						if (existing.has(key)) return;

						const child = frappe.model.add_child(
							frm.doc,
							"Receipt Payment",
							"receipt_payments",
						);
						frappe.model.set_value(child.doctype, child.name, {
							payment_entry: data.payment_entry,
							sales_invoice: data.sales_invoice || "",
							invoice_date: data.invoice_date || "",
							amount_due: data.amount_due,
							amount_received: data.amount_received,
							balance_due: data.balance_due,
							payment_method: data.payment_method || "",
							receiving_account: data.receiving_account || "",
							reference_no: data.reference_no || "",
							reference_date: data.reference_date || null,
						});
						existing.add(key);
						added++;
					});

					frm.refresh_field("receipt_payments");
					recompute_totals(frm);

					if (added === 0) {
						frappe.msgprint(
							__("All rows from this Payment Entry are already in the Receipt."),
						);
					} else {
						frappe.show_alert({
							message: __("{0} row(s) added from Payment Entry {1}", [added, pe]),
							indicator: "green",
						});
					}

					dialog.hide();
				},
			});
		},
	});

	dialog.fields_dict.payment_entry.$input.on("change", function () {
		const pe = $(this).val();
		if (!pe) {
			dialog.fields_dict.preview.$wrapper.html("");
			return;
		}
		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.receipt.receipt.get_payment_entry_details",
			args: { payment_entry: pe },
			callback(r) {
				if (!r.message?.rows?.length) {
					dialog.fields_dict.preview.$wrapper.html(
						`<p class="text-muted">${__("No Sales Invoice references found in this Payment Entry.")}</p>`,
					);
					return;
				}
				const rows = r.message.rows;
				let html = `<table class="table table-bordered table-condensed">
					<thead><tr>
						<th>${__("Invoice")}</th>
						<th>${__("Date")}</th>
						<th>${__("Amount Due")}</th>
						<th>${__("Amount Received")}</th>
					</tr></thead><tbody>`;
				rows.forEach((d) => {
					html += `<tr>
						<td>${frappe.escape_html(d.sales_invoice || "—")}</td>
						<td>${d.invoice_date || "—"}</td>
						<td>${format_currency(d.amount_due)}</td>
						<td>${format_currency(d.amount_received)}</td>
					</tr>`;
				});
				html += `</tbody></table>`;
				html += `<p class="text-muted">${__("Mode: {0} | Account: {1}", [
					r.message.mode_of_payment || "—",
					r.message.paid_to || "—",
				])}</p>`;
				dialog.fields_dict.preview.$wrapper.html(html);
			},
		});
	});

	dialog.show();
}
