frappe.ui.form.on("Sales Invoice", {
	onload(frm) {
		if (frm.is_new()) _sync_customer_withholding(frm, true);
	},

	customer(frm) {
		_sync_customer_withholding(frm, true);
	},

	apply_tds(frm) {
		_restore_required_withholding(frm);
	},

	validate(frm) {
		_sync_customer_withholding(frm, false);
	},

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

	custom_placement_transaction_type(frm) {
		_setup_item_query(frm);
	},
});

frappe.ui.form.on("Sales Invoice Item", {
	item_code(frm, cdt, cdn) {
		_on_item_change(frm, cdt, cdn);
	},
});

let _contract_data_cache = {};
let _customer_withholding_cache = {};

function _sync_customer_withholding(frm, notify) {
	if (frm.doc.docstatus !== 0 || frm.doc.is_opening === "Yes") return;

	const customer = frm.doc.customer;
	if (Object.prototype.hasOwnProperty.call(_customer_withholding_cache, customer)) {
		_apply_customer_withholding(frm, _customer_withholding_cache[customer], notify);
		return;
	}

	_fetch_customer_withholding(customer, (info) => {
		_apply_customer_withholding(frm, info, notify);
	});
}

function _restore_required_withholding(frm) {
	if (frm.doc.docstatus !== 0 || frm.doc.apply_tds || frm._nbs_setting_apply_tds) return;
	if (frm.doc.is_opening === "Yes") return;

	const customer = frm.doc.customer;
	const cached = _customer_withholding_cache[customer];
	if (cached !== undefined) {
		_restore_withholding_if_required(frm, cached);
		return;
	}

	_fetch_customer_withholding(customer, (info) => {
		_restore_withholding_if_required(frm, info);
	});
}

function _apply_customer_withholding(frm, info, notify) {
	if (!info || !info.category || frm.doc.apply_tds) return;

	_set_apply_tds(frm, 1);

	if (notify) {
		frappe.show_alert(
			{
				message: __(
					"Tax Withholding Category {0} is set for {1}. Tax withholding enabled.",
					[info.category, frm.doc.customer]
				),
				indicator: "blue",
			},
			5
		);
	}
}

function _restore_withholding_if_required(frm, info) {
	if (!info || !info.category) return;

	_set_apply_tds(frm, 1);
	frappe.show_alert(
		{
			message: __(
				"Tax withholding is required for {0} (Category: {1}). The checkbox was re-enabled.",
				[frm.doc.customer, info.category]
			),
			indicator: "orange",
		},
		7
	);
}

function _set_apply_tds(frm, value) {
	frm._nbs_setting_apply_tds = true;
	frm.set_value("apply_tds", value).finally(() => {
		frm._nbs_setting_apply_tds = false;
	});
}

function _fetch_customer_withholding(customer, callback) {
	if (!customer) {
		callback(null);
		return;
	}

	frappe.db.get_value(
		"Customer",
		customer,
		["tax_withholding_category", "tax_withholding_group"],
		(r) => {
			const category = r && (r.tax_withholding_category || r.tax_withholding_group);
			const info = category ? { category } : null;
			_customer_withholding_cache[customer] = info;
			callback(info);
		}
	);
}

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
	const ttype = frm.doc.custom_placement_transaction_type;
	const cached = _contract_data_cache;
	const analyzer_item = cached?.name === contract ? cached.analyzer_pid : null;

	if (ttype === "Ownership Transfer") {
		frm.set_query(item_field, child_table, () => ({
			filters: analyzer_item ? { name: analyzer_item } : {},
		}));
		return;
	}

	const filters = analyzer_item ? { analyzer_item } : { contract_name: contract };
	if (ttype === "Contract Reagent Sale") filters.reagent_role = "Test Reagent";
	if (ttype === "Contract Consumable Replenishment")
		filters.reagent_role = "Non-Test Consumable";

	frm.set_query(item_field, child_table, () => ({
		query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
		filters,
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
