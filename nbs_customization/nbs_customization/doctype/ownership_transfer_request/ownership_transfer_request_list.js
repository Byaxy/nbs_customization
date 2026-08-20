frappe.listview_settings["Ownership Transfer Request"] = {
	get_indicator(doc) {
		const map = {
			"Draft": [__("Draft"), "gray"],
			"Pending Finance Review": [__("Pending Finance Review"), "orange"],
			"Pending Legal Review": [__("Pending Legal Review"), "orange"],
			"Approved": [__("Approved"), "blue"],
			"Transfer Completed": [__("Transfer Completed"), "green"],
		};
		return map[doc.status] || [__("Unknown"), "gray"];
	},
};
