frappe.ui.form.on("Reagent Specification", {
	setup(frm) {
		frm.set_query("item", () => ({
			filters: {
				is_stock_item: 1,
				custom_analyzer_profile: ["is", "not set"],
			},
		}));
	},

	refresh(frm) {
		_toggle_sections(frm);
	},

	item(frm) {
		_set_item_defaults(frm);
	},

	reagent_role(frm) {
		_toggle_sections(frm);
		_set_item_defaults(frm);
	},
});

function _toggle_sections(frm) {
	const is_reagent = frm.doc.reagent_role === "Test Reagent";
	const is_consumable = frm.doc.reagent_role === "Non-Test Consumable";
	frm.toggle_display("test_reagent_details_section", is_reagent);
	frm.toggle_display("non_test_consumable_details_section", is_consumable);
}

function _set_item_defaults(frm) {
	if (!frm.doc.item) return;

	frappe.db
		.get_value("Item", frm.doc.item, ["stock_uom", "valuation_rate", "last_purchase_rate"])
		.then((r) => {
			const item = r.message || {};
			frm.set_value("pack_uom", item.stock_uom || null);
			const cost = item.valuation_rate || item.last_purchase_rate || 0;
			if (frm.doc.reagent_role === "Test Reagent") {
				frm.set_value("default_cogs_per_pack", cost);
				frm.set_value("default_cogs_per_unit", 0);
			} else if (frm.doc.reagent_role === "Non-Test Consumable") {
				frm.set_value("default_cogs_per_unit", cost);
				frm.set_value("default_cogs_per_pack", 0);
			}
		});
}
