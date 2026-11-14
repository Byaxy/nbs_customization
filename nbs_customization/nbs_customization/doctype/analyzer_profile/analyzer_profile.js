// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Analyzer Profile", {
	setup(frm) {
		frm.set_query("analyzer_item", () => {
			const filters = {
				custom_is_placement_item: 1,
				custom_reagent_specification: ["is", "not set"],
				custom_analyzer_profile: frm.is_new() ? ["is", "not set"] : frm.doc.name,
			};
			return { filters };
		});
		frm.set_query("test_parameter", "reagents", () => ({
			query: "nbs_customization.utils.placement.spec_lines.get_test_parameters",
		}));
		frm.set_query("reagent_item", "reagents", () => ({
			filters: placement_reagent_filters(),
		}));
		frm.set_query("item", "consumables", () => ({
			filters: placement_reagent_filters(),
		}));
		frm.set_query("item", "maintenance", () => ({
			filters: placement_reagent_filters(),
		}));
	},
});

function placement_reagent_filters() {
	return {
		custom_is_placement_item: 1,
		custom_reagent_specification: ["is", "set"],
	};
}
