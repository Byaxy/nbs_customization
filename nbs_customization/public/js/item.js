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

	frm.set_query("custom_instrument_specification", function () {
		return {
			filters: {
				item: ["in", [frm.doc.name, ""]],
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

	if (show) {
		frm.set_df_property(
			"custom_instrument_specification",
			"description",
			__(
				"Select the Instrument Specification if this item is an analyzer. Defines supported tests and consumables.",
			),
		);
		frm.set_df_property(
			"custom_reagent_specification",
			"description",
			__("Select the Reagent Specification if this item is a reagent or consumable."),
		);
	}
}
