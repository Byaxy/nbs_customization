// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Customer Delivery Note", {
	setup(frm) {
		frm.set_query("sales_order", function () {
			return {
				query: "nbs_customization.controllers.sales_order.sales_order_query",
				filters: { current_doc: frm.doc.name || "" },
			};
		});
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.sales_order) {
			fetch_sales_order_data(frm);
		}
	},

	refresh(frm) {
		set_address_contact_filters(frm);
		set_items_editable_state(frm);

		if (!frm.doc.date) {
			frm.set_value("date", frappe.datetime.get_today());
		}

		// For existing saved docs (not new, not dirty), just refresh the grid display.
		// The server already persisted correct data via _sync_from_sales_order on save.
		if (!frm.is_new() && frm.doc.sales_order) {
			frm.refresh_field("items");
		}
	},

	onload_post_render: function (frm) {
		setup_sales_order_redirect(frm);
	},

	sales_order: function (frm) {
		if (!frm.doc.sales_order) {
			frm.set_df_property("items", "cannot_add_rows", false);
			frm.set_df_property("items", "cannot_delete_rows", false);
			return;
		}

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Customer Delivery Note",
				filters: {
					sales_order: frm.doc.sales_order,
					docstatus: ["<", 2],
					...(frm.doc.__islocal ? {} : { name: ["!=", frm.doc.name] }),
				},
				fields: ["name"],
				limit: 1,
			},
			callback: function (r) {
				if (r.message && r.message.length > 0) {
					frappe.msgprint({
						title: __("Sales Order Already Linked"),
						indicator: "red",
						message: __(
							'This Sales Order is already linked to Customer Delivery Note: <a href="/app/customer-delivery-note/{0}" target="_blank">{0}</a>',
							[r.message[0].name],
						),
					});
					frm.set_value("sales_order", "");
					return;
				}

				fetch_sales_order_data(frm);
			},
		});
	},

	customer_address: function (frm) {
		update_address_display(frm, "customer_address", "address_display");
	},

	shipping_address_name: function (frm) {
		update_address_display(frm, "shipping_address_name", "shipping_address");
	},

	on_submit(frm) {
		frm.reload_doc();
	},

	on_cancel(frm) {
		frm.reload_doc();
	},
});

// ---------------------------------------------------------------------------
// Core helper: fetch SO data from server and populate the form
// ---------------------------------------------------------------------------
function fetch_sales_order_data(frm) {
	if (!frm.doc.sales_order) return;

	// Use frappe.client.get for a guaranteed fresh server fetch
	frappe.call({
		method: "frappe.client.get",
		args: {
			doctype: "Sales Order",
			name: frm.doc.sales_order,
		},
		freeze: true,
		freeze_message: __("Loading Sales Order data..."),
		callback: function (r) {
			if (!r.message) {
				frappe.msgprint(__("Could not fetch Sales Order data. Please try again."));
				return;
			}

			const so = r.message;

			frm.set_value("customer", so.customer);

			frm.set_value("customer_address", so.customer_address || null);
			frm.set_value(
				"shipping_address_name",
				so.shipping_address_name || so.customer_address || null,
			);

			set_address_contact_filters(frm);

			frm.clear_table("items");

			(so.items || []).forEach((item) => {
				const row = frm.add_child("items");
				row.item_code = item.item_code;
				row.description = item.description;
				row.qty_requested = item.qty;
				row.qty_supplied = item.qty;
				row.balance_left = 0;
			});

			frm.refresh_field("items");

			set_items_editable_state(frm);
		},
	});
}

// ---------------------------------------------------------------------------
// Address display helpers
// ---------------------------------------------------------------------------
function update_address_display(frm, address_field, display_field) {
	const address_name = frm.doc[address_field];
	if (!address_name) {
		frm.set_value(display_field, "");
		return;
	}

	frappe.call({
		method: "frappe.contacts.doctype.address.address.get_address_display",
		args: { address_dict: address_name },
		callback: function (r) {
			if (r.message) {
				frm.set_value(display_field, r.message);
			}
		},
	});
}

// ---------------------------------------------------------------------------
// Grid editability — lock rows when a Sales Order is selected
// ---------------------------------------------------------------------------
function set_items_editable_state(frm) {
	const locked = Boolean(frm.doc.sales_order);
	frm.set_df_property("items", "cannot_add_rows", locked);
	frm.set_df_property("items", "cannot_delete_rows", locked);
}

// ---------------------------------------------------------------------------
// Address / contact field query filters (filtered by customer)
// ---------------------------------------------------------------------------
function set_address_contact_filters(frm) {
	const customer_filter = frm.doc.customer
		? {
				query: "frappe.contacts.doctype.address.address.address_query",
				filters: { link_doctype: "Customer", link_name: frm.doc.customer },
			}
		: { filters: [["name", "=", ""]] };

	frm.set_query("customer_address", () => customer_filter);
	frm.set_query("shipping_address_name", () => customer_filter);

	frm.set_query("received_by", function () {
		if (!frm.doc.customer) {
			return { filters: [["name", "=", ""]] };
		}
		return {
			query: "frappe.contacts.doctype.contact.contact.contact_query",
			filters: { link_doctype: "Customer", link_name: frm.doc.customer },
		};
	});
}

// ---------------------------------------------------------------------------
// Guard: redirect user to fill Sales Order first before touching dependent fields
// ---------------------------------------------------------------------------
function setup_sales_order_redirect(frm) {
	const dependent_fields = [
		"customer",
		"customer_address",
		"shipping_address_name",
		"received_by",
	];

	dependent_fields.forEach(function (fieldname) {
		const field = frm.fields_dict[fieldname];
		if (field && field.$wrapper) {
			field.$wrapper.find("input, .link-btn").on("click", function (e) {
				if (!frm.doc.sales_order) {
					e.preventDefault();
					frappe.show_alert(
						{
							message: __("Please select a Sales Order first"),
							indicator: "orange",
						},
						3,
					);
					frm.scroll_to_field("sales_order");
					setTimeout(() => {
						const so_input = frm.fields_dict.sales_order.$input;
						if (so_input) so_input.focus();
					}, 100);
				}
			});
		}
	});
}
