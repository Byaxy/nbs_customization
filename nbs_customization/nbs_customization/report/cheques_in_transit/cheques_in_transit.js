// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.query_reports["Cheques in Transit"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "account",
			label: __("Clearing Account"),
			fieldtype: "MultiSelectList",
			options: "Account",
			get_data(txt) {
				const company = frappe.query_report.get_filter_value("company");
				return frappe.db.get_link_options("Account", txt, {
					company: company,
					is_group: 0,
				});
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "payment_type",
			label: __("Direction"),
			fieldtype: "Select",
			options: "\nInward\nOutward\nPay\nReceive",
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Autocomplete",
			options: "Customer\nSupplier\nEmployee\nPayee",
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Data",
		},
		{
			fieldname: "reference_no",
			label: __("Cheque No"),
			fieldtype: "Data",
		},
		{
			fieldname: "include_cleared",
			label: __("Include Cleared"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "include_returned",
			label: __("Include Returned"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "days_outstanding_from",
			label: __("Days Outstanding ≥"),
			fieldtype: "Int",
		},
	],
};
