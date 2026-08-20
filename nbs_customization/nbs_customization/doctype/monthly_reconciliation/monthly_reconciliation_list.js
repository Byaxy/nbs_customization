frappe.listview_settings["Monthly Reconciliation"] = {
	get_indicator(doc) {
		const map = {
			"Compliant": [__("Compliant"), "green"],
			"Shortfall": [__("Shortfall"), "orange"],
			"Grace Period": [__("Grace Period"), "blue"],
			"Breach": [__("Breach"), "red"],
		};
		return map[doc.compliance_status] || [__("Unknown"), "gray"];
	},
};
