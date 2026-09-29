frappe.listview_settings["Revenue Share Statement"] = {
	get_indicator(doc) {
		const map = {
			Draft: [__("Draft"), "gray"],
			Generated: [__("Generated"), "blue"],
			Invoiced: [__("Invoiced"), "green"],
		};
		return map[doc.status] || [__("Unknown"), "gray"];
	},
};
