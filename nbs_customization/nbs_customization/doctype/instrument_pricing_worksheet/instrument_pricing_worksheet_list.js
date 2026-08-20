frappe.listview_settings["Instrument Pricing Worksheet"] = {
	get_indicator: function (doc) {
		const STATUSES = {
			Draft: [__("Draft"), "orange"],
			Approved: [__("Approved"), "green"],
			"Applied to Contract": [__("Applied to Contract"), "purple"],
			Cancelled: [__("Cancelled"), "red"],
		};
		return STATUSES[doc.status] || [__(doc.status), "gray"];
	},
};
