frappe.listview_settings["Analyzer Deployment"] = {
	get_indicator(doc) {
		const map = {
			"Deployed": [__("Deployed"), "green"],
			"Under Service": [__("Under Service"), "orange"],
			"Temporarily Retrieved": [__("Temporarily Retrieved"), "blue"],
			"Permanently Retrieved": [__("Permanently Retrieved"), "gray"],
		};
		return map[doc.deployment_status] || [__("Unknown"), "gray"];
	},
};
