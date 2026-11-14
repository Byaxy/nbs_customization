frappe.ui.form.on("Delivery Note", {
	refresh: function (frm) {
		add_shipment_logic(frm);
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
					"This is a Loan Conversion Waybill. Items cannot be added, removed, or reordered. Quantities are set from the loan conversion process."
				),
				"yellow",
				true
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

function add_shipment_logic(frm) {
	frm.remove_custom_button(__("Shipment"), __("View"));

	if (frm.doc.docstatus !== 1) return;

	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Shipment",
			filters: [["Shipment Delivery Note", "delivery_note", "=", frm.doc.name]],
			fields: ["name"],
			limit: 1,
		},
		callback(r) {
			if (!r.message || !r.message.length) return;

			const shipment_name = r.message?.length ? r.message[0].name : null;

			if (!shipment_name) return;

			setTimeout(() => {
				frm.page.remove_inner_button(__("Shipment"), __("Create"));
			}, 100);

			frm.add_custom_button(
				__("Shipment"),
				() => frappe.set_route("Form", "Shipment", shipment_name),
				__("View")
			);
		},
	});
}

// === PLACEMENT CONTRACT SUPPORT ===

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		_setup_placement_contract(frm);
	},

	custom_instrument_placement_contract(frm) {
		_on_contract_change(frm);
	},

	custom_placement_transaction_type(frm) {
		_setup_item_query(frm);
	},

	customer(frm) {
		_clear_contract_on_customer_change(frm);
	},
});

frappe.ui.form.on("Delivery Note Item", {
	item_code(frm, cdt, cdn) {
		_on_item_change(frm, cdt, cdn);
	},
});

let _contract_data_cache = {};

function _setup_placement_contract(frm) {
	_setup_contract_query(frm);
	_refresh_contract_indicator(frm);
	_sync_transaction_type_options(frm);
	_setup_item_query(frm);
}

function _setup_contract_query(frm) {
	frm.set_query("custom_instrument_placement_contract", () => ({
		filters: {
			customer: frm.doc.customer,
			contract_status: ["in", ["Active", "Ownership Pending"]],
		},
	}));
}

function _on_contract_change(frm) {
	const contract_name = frm.doc.custom_instrument_placement_contract;

	if (!contract_name) {
		_contract_data_cache = {};
		frm.set_value("selling_price_list", null);
		_sync_transaction_type_options(frm);
		_reset_item_query(frm);
		_refresh_contract_indicator(frm);
		return;
	}

	frappe.call({
		method: "frappe.client.get",
		args: {
			doctype: "Instrument Placement Contract",
			name: contract_name,
		},
		callback(r) {
			if (!r.message) return;
			const contract = r.message;
			_contract_data_cache = contract;

			if (contract.contract_price_list) {
				frm.set_value("selling_price_list", contract.contract_price_list);
				frm.trigger("selling_price_list");
			}

			_sync_transaction_type_options(frm);
			_setup_item_query(frm);
			_refresh_contract_indicator(frm);
		},
	});
}

function _sync_transaction_type_options(frm) {
	if (frm.doc.docstatus !== 0) return;

	const field = "custom_placement_transaction_type";
	const contract = frm.doc.custom_instrument_placement_contract;
	if (!contract) {
		frm.toggle_display(field, false);
		if (frm.doc[field]) frm.set_value(field, null);
		return;
	}

	frm.toggle_display(field, true);
	const cached = _contract_data_cache;
	if (cached && cached.name === contract) {
		_apply_transaction_type_options(frm, cached.contract_type);
		return;
	}

	frappe.db.get_value("Instrument Placement Contract", contract, "contract_type").then((r) => {
		if (frm.doc.custom_instrument_placement_contract !== contract) return;
		if (r.message) _apply_transaction_type_options(frm, r.message.contract_type);
	});
}

function _apply_transaction_type_options(frm, contract_type) {
	const field = "custom_placement_transaction_type";
	const options =
		contract_type === "CPT"
			? ["", "Contract Free Issue", "Contract Consumable Free Issue"]
			: ["", "Contract Reagent Sale", "Contract Consumable Replenishment"];
	frm.set_df_property(field, "options", options.join("\n"));
	if (!options.includes(frm.doc[field] || "")) frm.set_value(field, null);
	frm.refresh_field(field);
}

function _clear_contract_on_customer_change(frm) {
	const contract = frm.doc.custom_instrument_placement_contract;
	if (!contract) return;
	const customer = frm.doc.customer;
	frappe.db.get_value("Instrument Placement Contract", contract, "customer").then((r) => {
		if (!r.message || r.message.customer === customer) return;
		frm.set_value("custom_instrument_placement_contract", null);
		frm.set_value("custom_placement_transaction_type", null);
		frappe.show_alert({
			message: __("Contract cleared because the customer changed."),
			indicator: "orange",
		});
	});
}

function _setup_item_query(frm) {
	const contract = frm.doc.custom_instrument_placement_contract;
	if (!contract) {
		_reset_item_query(frm);
		return;
	}

	frm.set_query(_get_item_field(frm), _get_child_table(frm), () => ({
		query: "nbs_customization.utils.placement.valid_items.get_contract_placement_items",
		filters: {
			contract: frm.doc.custom_instrument_placement_contract,
			transaction_type: frm.doc.custom_placement_transaction_type,
		},
	}));
}

function _reset_item_query(frm) {
	frm.set_query(_get_item_field(frm), _get_child_table(frm), () => ({}));
}

function _on_item_change(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !frm.doc.custom_instrument_placement_contract) return;

	const contract = _contract_data_cache;
	if (contract && contract.contract_price_list) {
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Item Price",
				filters: {
					item_code: row.item_code,
					price_list: contract.contract_price_list,
					selling: 1,
				},
				fieldname: "price_list_rate",
			},
			callback(r) {
				if (r.message && r.message.price_list_rate) {
					frappe.model.set_value(cdt, cdn, "rate", r.message.price_list_rate);
				}
			},
		});
	}

	frappe.db.get_value("Item", row.item_code, "description", (r) => {
		if (r && r.description) {
			frappe.model.set_value(cdt, cdn, "description", r.description);
		}
	});
}

function _refresh_contract_indicator(frm) {
	const contract = frm.doc.custom_instrument_placement_contract;
	if (!contract) return;

	const contract_type = _contract_data_cache?.contract_type || "";
	const indicator_color = contract_type === "CPT" ? "blue" : "green";
	frm.dashboard.add_comment(
		`<span class="indicator ${indicator_color}">
			${__("Linked to Placement Contract: {0} — {1}", [contract, contract_type])}
		</span>`
	);
}

function _get_child_table(frm) {
	const map = {
		"Sales Order": "items",
		"Delivery Note": "items",
		"Sales Invoice": "items",
	};
	return map[frm.doctype] || "items";
}

function _get_item_field(frm) {
	return "item_code";
}

// Prevent manual addition of rows through any means
frappe.ui.form.on("Delivery Note Item", {
	items_add: function (frm, cdt, cdn) {
		// If this is a loan conversion waybill and someone tries to add a row
		if (frm.doc.custom_waybill_type === "Loan Conversion Waybill" && frm.doc.docstatus === 0) {
			frappe.show_alert({
				message: __(
					"Cannot add items to a Loan Conversion Waybill. Please use the loan conversion process."
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
