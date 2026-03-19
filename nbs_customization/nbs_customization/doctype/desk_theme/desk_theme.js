// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt
//
// Client script for the Desk Theme DocType form.
// Registered in hooks.py under doctype_js.

frappe.ui.form.on("Desk Theme", {
	refresh(frm) {
		// ---- Apply Theme button ----------------------------------------
		frm.add_custom_button(
			__("Apply Theme"),
			() => {
				frm.save().then(() => {
					if (window.NBSTheme) {
						window.NBSTheme.applyAndReload();
					} else {
						localStorage.removeItem("nbs_theme_v1");
						window.location.reload();
					}
				});
			},
			__("Actions"),
		);

		// ---- Reset to Defaults button ------------------------------------
		frm.add_custom_button(
			__("Reset to Defaults"),
			() => {
				frappe.confirm(
					__("Reset all colors to NBS defaults? This cannot be undone."),
					() => {
						frm.call("reset_to_defaults")
							.then(() => {
								frappe.show_alert({
									message: __("Theme reset to NBS defaults."),
									indicator: "green",
								});
								localStorage.removeItem("nbs_theme_v1");
								// Give the server a moment to commit, then reload
								setTimeout(() => window.location.reload(), 500);
							})
							.catch(() => {
								frappe.msgprint(__("Reset failed. Please try again."));
							});
					},
				);
			},
			__("Actions"),
		);

		// ---- Helpful note in the form -----------------------------------
		if (!frm.doc.__islocal) {
			frm.set_intro(
				__(
					"Edit colors in the tabs below, then click <b>Actions → Apply Theme</b> to save and apply changes immediately.",
				),
				"blue",
			);
		}
	},
});
