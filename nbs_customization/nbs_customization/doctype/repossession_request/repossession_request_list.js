frappe.listview_settings["Repossession Request"] = {
	get_indicator(doc) {
		const map = {
			"Draft": [__("Draft"), "gray"],
			"Pending Approval": [__("Pending Approval"), "orange"],
			"Approved": [__("Approved"), "blue"],
			"Analyzer Retrieved": [__("Analyzer Retrieved"), "green"],
			"Closed": [__("Closed"), "darkgray"],
		};
		return map[doc.status] || [__("Unknown"), "gray"];
	},
};
