// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Waybill", {
	refresh(frm) {
		set_address_contact_filters(frm);
		set_item_query(frm);
		if (frm.doc.docstatus === 1) {
			frm.set_read_only();
		}
	},

	onload_post_render(frm) {
		setup_customer_redirect(frm);
	},

	customer(frm) {
		if (!frm.doc.customer) {
			clear_customer_fields(frm);
			return;
		}
		load_customer_addresses(frm);
	},

	customer_address(frm) {
		update_address_display(frm, "customer_address", "address_display");
	},

	shipping_address_name(frm) {
		update_address_display(frm, "shipping_address_name", "shipping_address");
	},

	source_warehouse(frm) {
		set_item_query(frm);
		if (frm.doc.items && frm.doc.items.length > 0) {
			const has_data = frm.doc.items.some((row) => row.item_code);

			if (has_data) {
				frappe.confirm(
					__("Changing the source warehouse will clear existing items. Continue?"),
					() => {
						frm.clear_table("items");
						frm.add_child("items");
						frm.refresh_field("items");
					},
				);
			} else {
				frm.refresh_field("items");
			}
		}
	},
});

/* ------------------------------------------------------------------ */
/* CUSTOMER HELPERS                                                     */
/* ------------------------------------------------------------------ */

function load_customer_addresses(frm) {
	frappe.call({
		method: "frappe.contacts.doctype.address.address.get_default_address",
		args: { doctype: "Customer", name: frm.doc.customer },
		callback: (r) => r.message && frm.set_value("customer_address", r.message),
	});

	frappe.call({
		method: "frappe.contacts.doctype.address.address.get_default_address",
		args: { doctype: "Customer", name: frm.doc.customer, sort_key: "is_shipping_address" },
		callback: (r) => r.message && frm.set_value("shipping_address_name", r.message),
	});
}

function clear_customer_fields(frm) {
	frm.set_value({
		customer_address: "",
		shipping_address_name: "",
		received_by: "",
		address_display: "",
		shipping_address: "",
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

/* ------------------------------------------------------------------ */
/* FILTERS                                                             */
/* ------------------------------------------------------------------ */

function set_address_contact_filters(frm) {
	const empty = { filters: [["name", "=", ""]] };

	frm.set_query("customer_address", () =>
		frm.doc.customer
			? {
					query: "frappe.contacts.doctype.address.address.address_query",
					filters: { link_doctype: "Customer", link_name: frm.doc.customer },
				}
			: empty,
	);

	frm.set_query("shipping_address_name", () =>
		frm.doc.customer
			? {
					query: "frappe.contacts.doctype.address.address.address_query",
					filters: { link_doctype: "Customer", link_name: frm.doc.customer },
				}
			: empty,
	);

	frm.set_query("received_by", () =>
		frm.doc.customer
			? {
					query: "frappe.contacts.doctype.contact.contact.contact_query",
					filters: { link_doctype: "Customer", link_name: frm.doc.customer },
				}
			: empty,
	);
}

/* ------------------------------------------------------------------ */
/* UX SAFETY                                                           */
/* ------------------------------------------------------------------ */

function setup_customer_redirect(frm) {
	["customer_address", "shipping_address_name", "received_by"].forEach((fieldname) => {
		const field = frm.fields_dict[fieldname];
		if (!field?.$wrapper) return;

		field.$wrapper.on("click", "input, .link-btn", (e) => {
			if (!frm.doc.customer) {
				e.preventDefault();
				frappe.show_alert(
					{ message: __("Please select a Customer first"), indicator: "orange" },
					3,
				);
				frm.scroll_to_field("customer");
			}
		});
	});
}

function set_item_query(frm) {
	frm.fields_dict.items.grid.get_field("item_code").get_query = () => {
		if (!frm.doc.source_warehouse) {
			return {
				filters: { name: ["=", ""] },
			};
		}
		return {
			query: "nbs_customization.nbs_customization.doctype.loan_waybill.loan_waybill.get_items_with_stock",
			filters: { warehouse: frm.doc.source_warehouse },
		};
	};
}
