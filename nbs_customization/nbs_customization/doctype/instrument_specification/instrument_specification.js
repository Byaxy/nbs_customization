frappe.ui.form.on("Instrument Specification", {
	setup(frm) {
		frm.set_query("item", () => ({
			filters: {
				custom_is_placement_item: 1,
				is_stock_item: 1,
			},
		}));
		_filter_reagent_queries(frm);
		_filter_consumable_queries(frm);
	},
});

frappe.ui.form.on("Instrument Test Method", {
	required_reagent(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.required_reagent) return;

		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Reagent Specification",
				filters: { item: row.required_reagent },
				fieldname: [
					"reagent_role",
					"default_pack_volume_ml",
					"default_tests_per_pack",
					"default_cogs_per_pack",
				],
			},
			callback(r) {
				if (!r.message) return;

				if (r.message.reagent_role !== "Test Reagent") {
					frappe.msgprint({
						title: __("Invalid Reagent"),
						message: __(
							"Item {0} has Reagent Role '{1}'. Only Test Reagent items are allowed.",
							[row.required_reagent, r.message.reagent_role],
						),
						indicator: "red",
					});
					frappe.model.set_value(cdt, cdn, "required_reagent", null);
					return;
				}

				frappe.model.set_value(cdt, cdn, "default_pack_volume_ml", r.message.default_pack_volume_ml);
				frappe.model.set_value(cdt, cdn, "default_tests_per_pack", r.message.default_tests_per_pack);
				frappe.model.set_value(cdt, cdn, "default_cogs_per_pack", r.message.default_cogs_per_pack);
			},
		});
	},

	test_parameter(frm, cdt, cdn) {
		_check_duplicate_parameter(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Instrument Consumable Requirement", {
	consumable_item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.consumable_item) return;

		if (_check_duplicate_consumable(frm, cdt, cdn)) return;

		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Reagent Specification",
				filters: { item: row.consumable_item },
				fieldname: [
					"reagent_role",
					"default_consumption_qty",
					"default_consumption_frequency",
					"default_cogs_per_unit",
				],
			},
			callback(r) {
				if (!r.message) return;

				if (r.message.reagent_role !== "Non-Test Consumable") {
					frappe.msgprint({
						title: __("Invalid Consumable"),
						message: __(
							"Item {0} has Reagent Role '{1}'. Only Non-Test Consumable items are allowed.",
							[row.consumable_item, r.message.reagent_role],
						),
						indicator: "red",
					});
					frappe.model.set_value(cdt, cdn, "consumable_item", null);
					return;
				}

				frappe.model.set_value(cdt, cdn, "consumption_qty", r.message.default_consumption_qty);
				frappe.model.set_value(cdt, cdn, "consumption_frequency", r.message.default_consumption_frequency);
				frappe.model.set_value(cdt, cdn, "default_cogs_per_unit", r.message.default_cogs_per_unit);
			},
		});
	},
});

function _filter_reagent_queries(frm) {
	frm.set_query("required_reagent", "supported_test_methods", function () {
		const filters = { reagent_role: "Test Reagent" };
		if (frm.doc.analyzer_type) {
			filters.analyzer_type = frm.doc.analyzer_type;
		}
		return {
			query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
			filters: filters,
		};
	});
}

function _filter_consumable_queries(frm) {
	frm.set_query("consumable_item", "required_consumables", function () {
		const filters = { reagent_role: "Non-Test Consumable" };
		if (frm.doc.analyzer_type) {
			filters.analyzer_type = frm.doc.analyzer_type;
		}
		return {
			query: "nbs_customization.utils.placement.valid_items.get_valid_reagent_items",
			filters: filters,
		};
	});
}

function _check_duplicate_parameter(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.test_parameter) return;

	const child_table = frm.doc.supported_test_methods || [];
	const count = child_table.filter(
		(r) => r.test_parameter === row.test_parameter && r.name !== row.name,
	).length;

	if (count > 0) {
		frappe.msgprint({
			title: __("Duplicate Parameter"),
			message: __("Test Parameter {0} is already in the list.", [row.test_parameter]),
			indicator: "orange",
		});
		frappe.model.set_value(cdt, cdn, "test_parameter", null);
	}
}

function _check_duplicate_consumable(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.consumable_item) return false;

	const child_table = frm.doc.required_consumables || [];
	const duplicate = child_table.find(
		(r) => r.consumable_item === row.consumable_item && r.name !== row.name,
	);

	if (duplicate) {
		frappe.msgprint({
			title: __("Duplicate Consumable"),
			message: __("Consumable {0} is already in the list.", [row.consumable_item]),
			indicator: "orange",
		});
		frappe.model.set_value(cdt, cdn, "consumable_item", null);
		return true;
	}
	return false;
}
