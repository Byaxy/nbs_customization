frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		setTimeout(() => {
			frm.page.remove_inner_button(__("Delivery Note"), __("Create"));
		}, 100);

		_setup_placement_contract(frm);
	},

	custom_instrument_placement_contract(frm) {
		_on_contract_change(frm);
	},
});

frappe.ui.form.on("Sales Invoice Item", {
	item_code(frm, cdt, cdn) {
		_on_item_change(frm, cdt, cdn);
	},
});

let _contract_data_cache = {};

function _setup_placement_contract(frm) {
	_refresh_contract_indicator(frm);
	_setup_item_query(frm);
}

function _on_contract_change(frm) {
	const contract_name = frm.doc.custom_instrument_placement_contract;

	if (!contract_name) {
		_contract_data_cache = {};
		frm.set_value("selling_price_list", null);
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

			_setup_item_query(frm);
			_refresh_contract_indicator(frm);
		},
	});
}

function _setup_item_query(frm) {
	const contract = frm.doc.custom_instrument_placement_contract;
	if (!contract) return;

	const child_table = _get_child_table(frm);
	const item_field = _get_item_field(frm);

	frm.set_query(item_field, child_table, () => ({
		query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
		filters: { contract_name: contract },
	}));
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
