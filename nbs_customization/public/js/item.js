frappe.ui.form.on("Item", {
	setup(frm) {
		_setup_placement_fields(frm);
	},

	custom_is_placement_item(frm) {
		_toggle_placement_fields(frm);
	},
});

function _setup_placement_fields(frm) {
	_toggle_placement_fields(frm);

	frm.set_query("custom_analyzer_profile", function () {
		return {
			filters: {
				analyzer_item: ["in", [frm.doc.name, ""]],
			},
		};
	});

	frm.set_query("custom_reagent_specification", function () {
		return {
			filters: {
				item: ["in", [frm.doc.name, ""]],
			},
		};
	});
}

function _toggle_placement_fields(frm) {
	const show = frm.doc.custom_is_placement_item === 1;
	if (!show) return;

	frm.set_df_property(
		"custom_analyzer_profile",
		"description",
		__(
			"Select the Analyzer Profile if this item is an analyzer. It defines tests, reagents and consumables."
		)
	);
	frm.set_df_property(
		"custom_reagent_specification",
		"description",
		__("Select the Reagent Specification if this item is a reagent or consumable.")
	);
}
