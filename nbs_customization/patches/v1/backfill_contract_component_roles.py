# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe


def execute():
	contracts = frappe.get_all(
		"Instrument Placement Contract",
		filters={"pricing_worksheet": ("is", "set")},
		fields=["name", "pricing_worksheet"],
	)
	for contract in contracts:
		worksheet_lines = frappe.get_all(
			"Worksheet Test Reagent Line",
			filters={"parent": contract.pricing_worksheet, "parenttype": "Instrument Pricing Worksheet"},
			fields=["item_code", "test_parameter", "component_role"],
		)
		by_item_test = {}
		for line in worksheet_lines:
			by_item_test.setdefault((line.item_code, line.test_parameter), []).append(line)

		contract_lines = frappe.get_all(
			"Contract Test Reagent Line",
			filters={"parent": contract.name, "parenttype": "Instrument Placement Contract"},
			fields=["name", "item_code", "test_parameter", "component_role"],
		)
		for line in contract_lines:
			if line.component_role:
				continue
			matches = by_item_test.get((line.item_code, line.test_parameter), [])
			if len(matches) == 1:
				frappe.db.set_value(
					"Contract Test Reagent Line",
					line.name,
					"component_role",
					matches[0].component_role or "",
					update_modified=False,
				)
