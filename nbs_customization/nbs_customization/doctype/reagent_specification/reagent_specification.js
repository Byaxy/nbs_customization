frappe.ui.form.on("Reagent Specification", {
	setup(frm) {
		frm.set_query("item", () => ({
			filters: {
				custom_is_placement_item: 1,
				is_stock_item: 1,
			},
		}));
	},
	refresh(frm) {
		_toggle_sections(frm);
	},

	item(frm) {
		_fetch_product_landed_cost(frm);
	},

	reagent_role(frm) {
		_toggle_sections(frm);
		_fetch_product_landed_cost(frm);
	},
});

function _toggle_sections(frm) {
	const is_reagent = frm.doc.reagent_role === "Test Reagent";
	const is_consumable = frm.doc.reagent_role === "Non-Test Consumable";

	if (is_reagent) {
		frm.set_df_property("test_panel_group", "reqd", 1);
	} else {
		frm.set_df_property("test_panel_group", "reqd", 0);
	}
}

function _fetch_product_landed_cost(frm) {
	if (!frm.doc.item || !frm.doc.reagent_role) return;

	frappe.call({
		method: "nbs_customization.utils.placement.spec_lines.get_analyzer_landed_cost",
		args: { analyzer_item: frm.doc.item },
		callback(r) {
			if (!r.message || !(r.message.rate > 0)) return;
			if (frm.doc.reagent_role === "Test Reagent") {
				frm.set_value("default_cogs_per_pack", r.message.rate);
				frm.set_value("default_cogs_per_unit", null);
			} else {
				frm.set_value("default_cogs_per_unit", r.message.rate);
				frm.set_value("default_cogs_per_pack", null);
			}
		},
	});
}
