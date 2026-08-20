frappe.listview_settings["Instrument Placement Contract"] = {
	status_field: "contract_status",
	has_indicator_for_draft: 1,
	get_indicator(doc) {
		const status_map = {
			"Draft": [__("Draft"), "gray"],
			"Active": [__("Active"), "green"],
			"Fulfilled": [__("Fulfilled"), "blue"],
			"Breached": [__("Breached"), "red"],
			"Terminated": [__("Terminated"), "orange"],
			"Expired": [__("Expired"), "darkgray"],
		};
		if (doc.contract_status) {
			return status_map[doc.contract_status] || [__("Unknown"), "gray"];
		}
		// fallback when contract_status is not yet fetched
		if (doc.docstatus === 0) return [__("Draft"), "gray"];
		if (doc.docstatus === 1) return [__("Active"), "green"];
		if (doc.docstatus === 2) return [__("Cancelled"), "red"];
		return [__("Unknown"), "gray"];
	},
};
