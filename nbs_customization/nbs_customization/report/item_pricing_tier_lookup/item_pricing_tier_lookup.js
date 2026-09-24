// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
frappe.query_reports["Item Pricing Tier Lookup"] = {
	filters: [
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "pricing_mode", label: __("Mode"), fieldtype: "Select", options: "\nAuto\nManual" },
	],
};
