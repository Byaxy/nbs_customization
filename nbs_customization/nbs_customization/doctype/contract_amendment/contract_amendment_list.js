frappe.listview_settings["Contract Amendment"] = {
	get_indicator(doc) {
		const map = {
			Draft: [__("Draft"), "gray"],
			"Pending Customer Signature": [__("Pending Customer Signature"), "orange"],
			Approved: [__("Approved"), "blue"],
			Effective: [__("Effective"), "green"],
		};
		return map[doc.status] || [__("Unknown"), "gray"];
	},
};
