// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Promissory Note", {
	refresh(frm) {
		set_address_filters(frm);

		if (!frm.doc.date) {
			frm.set_value("date", frappe.datetime.get_today());
		}

		if (!frm.doc.naming_series) {
			frm.set_value("naming_series", "NBSPN-.YYYY./.MM./.####");
		}
	},

	onload_post_render: function (frm) {
		setup_sale_order_redirect(frm);
	},

	sales_order: function (frm) {
		if (frm.doc.sales_order) {
			// First, check if this Sales Order is already linked
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Promissory Note",
					filters: {
						sales_order: frm.doc.sales_order,
						name: ["!=", frm.doc.name || "new-promissory-note"],
						docstatus: ["!=", 2],
					},
					fields: ["name"],
					limit: 1,
				},
				callback: function (r) {
					if (r.message && r.message.length > 0) {
						// This SO is already linked!
						frappe.msgprint({
							title: __("Sales Order Already Linked"),
							indicator: "red",
							message: __(
								'This Sales Order is already linked to Promissory Note: <a href="/app/promissory-note/{0}" target="_blank">{0}</a>',
								[r.message[0].name],
							),
						});

						frm.set_value("sales_order", "");
						return;
					}

					// If not linked, proceed to fetch SO data (header + addresses only).
					fetch_sales_order_data(frm);
				},
			});
		}
	},

	customer_address: function (frm) {
		// Update address display when address changes
		if (frm.doc.customer_address) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: {
					address_dict: frm.doc.customer_address,
				},
				callback: function (r) {
					if (r.message) {
						frm.set_value("address_display", r.message);
					}
				},
			});
		} else {
			frm.set_value("address_display", "");
		}
	},

	shipping_address_name: function (frm) {
		// Update shipping address display when address changes
		if (frm.doc.shipping_address_name) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: {
					address_dict: frm.doc.shipping_address_name,
				},
				callback: function (r) {
					if (r.message) {
						frm.set_value("shipping_address", r.message);
					}
				},
			});
		} else {
			frm.set_value("shipping_address", "");
		}
	},
});

function setup_sale_order_redirect(frm) {
	const fields_requiring_sale_order = ["customer", "customer_address", "shipping_address_name"];

	fields_requiring_sale_order.forEach(function (fieldname) {
		const field = frm.fields_dict[fieldname];
		if (field && field.$wrapper) {
			field.$wrapper.find("input, .link-btn").on("click", function (e) {
				if (!frm.doc.sales_order) {
					e.preventDefault();
					frappe.show_alert(
						{
							message: __("Please select a Sale Order first"),
							indicator: "orange",
						},
						3,
					);
					frm.scroll_to_field("sales_order");
					setTimeout(() => frm.fields_dict.sales_order.$input.focus(), 100);
				}
			});
		}
	});
}

function fetch_sales_order_data(frm) {
	frappe.model.with_doc("Sales Order", frm.doc.sales_order, function () {
		let so = frappe.model.get_doc("Sales Order", frm.doc.sales_order);

		// 1. Set Header Fields
		frm.set_value("customer", so.customer);
		frm.set_value("customer_address", so.customer_address);
		frm.set_value("shipping_address_name", so.shipping_address_name || so.customer_address);

		// Items, totals, and status are computed server-side based on Sales Order minus delivered quantities.
		frm.set_df_property("items", "cannot_add_rows", true);
		frm.set_df_property("items", "cannot_delete_rows", true);
		frm.refresh_field("items");
	});
}

function set_address_filters(frm) {
	// Filter billing address to show only customer's addresses
	frm.set_query("customer_address", function () {
		if (!frm.doc.customer) {
			return { filters: [["name", "=", ""]] };
		}
		return {
			query: "frappe.contacts.doctype.address.address.address_query",
			filters: {
				link_doctype: "Customer",
				link_name: frm.doc.customer,
			},
		};
	});

	// Filter shipping address to show only customer's addresses
	frm.set_query("shipping_address_name", function () {
		if (!frm.doc.customer) {
			return { filters: [["name", "=", ""]] };
		}
		return {
			query: "frappe.contacts.doctype.address.address.address_query",
			filters: {
				link_doctype: "Customer",
				link_name: frm.doc.customer,
			},
		};
	});
}
