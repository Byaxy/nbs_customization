frappe.ui.form.on("Delivery Note", {
	refresh: function (frm) {
		// Only apply to loan conversion waybills
		if (frm.doc.custom_waybill_type === "Loan Conversion Waybill" && frm.doc.docstatus === 0) {
			// Hide add row button
			frm.fields_dict["items"].grid.add_rows_button.hide();

			// Hide delete button for each row
			frm.fields_dict["items"].grid.wrapper.find(".grid-delete-row").hide();

			// Disable drag and drop reordering
			frm.fields_dict["items"].grid.disable_reorder = true;

			// Add a warning message
			frm.dashboard.add_comment(
				__(
					"This is a Loan Conversion Waybill. Items cannot be added, removed, or reordered. Quantities are set from the loan conversion process.",
				),
				"yellow",
				true,
			);
		}
	},

	onload: function (frm) {
		// Apply restrictions on load as well
		if (frm.doc.custom_waybill_type === "Loan Conversion Waybill" && frm.doc.docstatus === 0) {
			// Prevent adding new rows via keyboard shortcuts
			frm.fields_dict["items"].grid.cannot_add_rows = true;

			// Set items grid to read-only mode for structural changes
			frm.fields_dict["items"].grid.df["allow_on_submit"] = 0;
		}
	},

	items_grid_render: function (frm, grid) {
		// Apply restrictions when grid is rendered
		if (frm.doc.custom_waybill_type === "Loan Conversion Waybill" && frm.doc.docstatus === 0) {
			// Hide delete buttons for each row
			setTimeout(function () {
				grid.wrapper.find(".grid-delete-row").hide();
				grid.wrapper.find(".grid-row-move").hide();
			}, 100);
		}
	},
	custom_waybill_type(frm) {
		if (frm.doc.custom_waybill_type !== "Loan Conversion Waybill") return;

		frm.set_value({
			custom_is_conversion: 1,
		});
	},
});

// Prevent manual addition of rows through any means
frappe.ui.form.on("Delivery Note Item", {
	items_add: function (frm, cdt, cdn) {
		// If this is a loan conversion waybill and someone tries to add a row
		if (frm.doc.custom_waybill_type === "Loan Conversion Waybill" && frm.doc.docstatus === 0) {
			frappe.show_alert({
				message: __(
					"Cannot add items to a Loan Conversion Waybill. Please use the loan conversion process.",
				),
				indicator: "red",
			});

			// Remove the newly added row
			frappe.model.remove_from_doclist(cdt, cdn);
			refresh_field("items");

			return false;
		}
	},
});
