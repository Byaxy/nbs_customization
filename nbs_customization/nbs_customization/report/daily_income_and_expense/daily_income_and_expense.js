// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Income and Expense"] = {
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
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "income_only",
			label: __("Income Only"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "expense_only",
			label: __("Expense Only"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "report_date",
			label: __("Date (Legacy)"),
			fieldtype: "Date",
			hidden: 1,
		},
	],
	onload(report) {
		// Backward compat: if URL has report_date, copy to from/to
		const rd = frappe.query_report.get_filter_value("report_date");
		if (rd) {
			report.set_filter_value("from_date", rd);
			report.set_filter_value("to_date", rd);
		}
	},
	validate() {
		const from_date = frappe.query_report.get_filter_value("from_date");
		const to_date = frappe.query_report.get_filter_value("to_date");
		if (from_date && to_date && from_date > to_date) {
			frappe.msgprint(__("From Date cannot be after To Date"));
			return false;
		}
		return true;
	},
};
