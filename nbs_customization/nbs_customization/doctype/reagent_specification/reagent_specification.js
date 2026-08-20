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

	reagent_role(frm) {
		_toggle_sections(frm);
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
