// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Promissory Note", {
	setup(frm) {
		// Lock the SO field picker to submitted SOs without an existing PN
		frm.set_query("sales_order", function () {
			return {
				query: "nbs_customization.controllers.sales_order.promissory_note_sales_order_query",
				filters: { current_doc: frm.doc.name || "" },
			};
		});

		set_address_filters(frm);
	},

	refresh(frm) {
		set_address_filters(frm);
		lock_items_if_so_linked(frm);

		if (!frm.doc.date) {
			frm.set_value("date", frappe.datetime.get_today());
		}
	},

	onload(frm) {
		// When opened via open_mapped_doc the SO is already set but the
		// sales_order change event won't fire. Detect and handle this.
		if (frm.is_new() && frm.doc.sales_order) {
			lock_items_if_so_linked(frm);
		}
	},

	sales_order(frm) {
		if (!frm.doc.sales_order) {
			// SO was cleared — unlock items
			frm.set_df_property("items", "cannot_add_rows", false);
			frm.set_df_property("items", "cannot_delete_rows", false);
			return;
		}
		lock_items_if_so_linked(frm);
	},

	customer_address(frm) {
		if (frm.doc.customer_address) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: { address_dict: frm.doc.customer_address },
				callback(r) {
					frm.set_value("address_display", r.message || "");
				},
			});
		} else {
			frm.set_value("address_display", "");
		}
	},

	shipping_address_name(frm) {
		if (frm.doc.shipping_address_name) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: { address_dict: frm.doc.shipping_address_name },
				callback(r) {
					frm.set_value("shipping_address", r.message || "");
				},
			});
		} else {
			frm.set_value("shipping_address", "");
		}
	},
});

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function lock_items_if_so_linked(frm) {
	const locked = !!frm.doc.sales_order;
	frm.set_df_property("items", "cannot_add_rows", locked);
	frm.set_df_property("items", "cannot_delete_rows", locked);
}

function set_address_filters(frm) {
	const customer_filter = () => {
		if (!frm.doc.customer) return { filters: [["name", "=", ""]] };
		return {
			query: "frappe.contacts.doctype.address.address.address_query",
			filters: { link_doctype: "Customer", link_name: frm.doc.customer },
		};
	};

	frm.set_query("customer_address", customer_filter);
	frm.set_query("shipping_address_name", customer_filter);
}
