// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Customer Delivery Note", {
	refresh(frm) {
		frm.set_query("sales_order", function () {
			return {
				filters: [
					["Sales Order", "docstatus", "=", 1],
					[
						"Sales Order",
						"name",
						"not in",
						"select sales_order from `tabCustomer Delivery Note` where docstatus < 2 and sales_order is not null",
					],
				],
			};
		});

		set_address_contact_filters(frm);
		frm.set_df_property("items", "cannot_add_rows", true);
		frm.set_df_property("items", "cannot_delete_rows", true);

		if (!frm.doc.date) {
			frm.set_value("date", frappe.datetime.get_today());
		}

		if (!frm.doc.naming_series) {
			frm.set_value("naming_series", "NBSDN-.YYYY./.MM./.####");
		}
	},

	onload_post_render: function (frm) {
		setup_sales_order_redirect(frm);
	},

	sales_order: function (frm) {
		if (frm.doc.sales_order) {
			// First, check if this Sales Order is already linked
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Customer Delivery Note",
					filters: {
						sales_order: frm.doc.sales_order,
						name: ["!=", frm.doc.name || "new-customer-delivery-note"],
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
								'This Sales Order is already linked to Customer Delivery Note: <a href="/app/customer-delivery-note/{0}" target="_blank">{0}</a>',
								[r.message[0].name],
							),
						});

						frm.set_value("sales_order", "");
						return;
					}

					// If not linked, proceed to fetch SO data
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

function fetch_sales_order_data(frm) {
	frappe.model.with_doc("Sales Order", frm.doc.sales_order, function () {
		let so = frappe.model.get_doc("Sales Order", frm.doc.sales_order);

		// 1. Set Header Fields
		frm.set_value("customer", so.customer);
		frm.set_value("customer_address", so.customer_address);
		frm.set_value("shipping_address_name", so.shipping_address_name || so.customer_address);

		// 2. Clear existing items in child table
		frm.clear_table("items");

		// 3. Loop through Sales Order items and add to child table
		so.items.forEach((item) => {
			let row = frm.add_child("items");
			row.item_code = item.item_code;
			row.item_description = item.description;
			row.qty_requested = item.qty;
			row.qty_supplied = item.qty;
			row.balance_left = 0;
		});

		// Refresh the table to show changes
		frm.refresh_field("items");

		// 4. Disable the "Add Row" button after populating items
		frm.set_df_property("items", "cannot_add_rows", true);

		// hide the delete button if you want to prevent row deletion
		frm.set_df_property("items", "cannot_delete_rows", true);
	});
}

function set_address_contact_filters(frm) {
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

	// Filter received by to show only customer's contacts
	frm.set_query("received_by", function () {
		if (!frm.doc.customer) {
			return { filters: [["name", "=", ""]] };
		}
		return {
			query: "frappe.contacts.doctype.contact.contact.contact_query",
			filters: {
				link_doctype: "Customer",
				link_name: frm.doc.customer,
			},
		};
	});
}

function setup_sales_order_redirect(frm) {
	const fields_requiring_sales_order = [
		"customer",
		"customer_address",
		"shipping_address_name",
		"received_by",
	];

	fields_requiring_sales_order.forEach(function (fieldname) {
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
					setTimeout(() => frm.fields_dict.sales_order.$input.focus(), 100);
				}
			});
		}
	});
}
