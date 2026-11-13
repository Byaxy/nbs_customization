frappe.listview_settings["Analyzer Deployment"] = {
	get_indicator(doc) {
		const map = {
			Draft: [__("Draft"), "gray"],
			Deployed: [__("Deployed"), "green"],
			"Under Service": [__("Under Service"), "orange"],
			"Temporarily Retrieved": [__("Temporarily Retrieved"), "blue"],
			"Permanently Retrieved": [__("Permanently Retrieved"), "red"],
		};
		return map[doc.deployment_status] || [__("Unknown"), "gray"];
	},
};
