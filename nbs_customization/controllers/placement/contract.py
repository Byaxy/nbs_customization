import frappe
from frappe.utils import today


@frappe.whitelist()
def make_deployment(source_name, target_doc=None):
	from frappe.model.mapper import get_mapped_doc

	def set_missing_values(source, target):
		target.deployment_status = "Draft"
		target.deployment_date = today()

	return get_mapped_doc(
		"Instrument Placement Contract",
		source_name,
		{
			"Instrument Placement Contract": {
				"doctype": "Analyzer Deployment",
				"field_map": {
					"name": "contract",
					"asset": "asset",
					"serial_no": "serial_no",
					"customer": "customer",
					"customer_name": "customer_name",
					"customer_site": "customer_site",
					"analyzer_pid": "analyzer_pid",
					"analyzer_description": "analyzer_description",
				},
				"validation": {
					"docstatus": ["=", 1],
				},
			},
		},
		target_doc,
		set_missing_values,
	)


@frappe.whitelist()
def decommission_analyzer(asset_name, reason=None):
	"""Scrap an unusable analyzer via the native Asset scrap flow.

	Requires no Deployed deployment and no Active contract link.
	"""
	from erpnext.assets.doctype.asset.depreciation import scrap_asset

	if frappe.db.get_value(
		"Analyzer Deployment", {"asset": asset_name, "deployment_status": "Deployed"}, "name"
	):
		frappe.throw(
			frappe._("Asset {0} has a Deployed deployment — retrieve it before decommissioning.").format(
				asset_name
			)
		)
	contract = frappe.db.get_value("Asset", asset_name, "custom_current_placement_contract")
	if (
		contract
		and frappe.db.get_value("Instrument Placement Contract", contract, "contract_status") == "Active"
	):
		frappe.throw(
			frappe._("Asset {0} is linked to Active contract {1} — close it first.").format(
				asset_name, contract
			)
		)
	scrap_asset(asset_name)
	return asset_name


@frappe.whitelist()
def make_repossession_request(source_name, target_doc=None):
	from frappe.model.mapper import get_mapped_doc

	def set_missing_values(source, target):
		deployment = frappe.db.get_value(
			"Analyzer Deployment",
			{"contract": source.name, "deployment_status": "Deployed"},
			"name",
		)
		if deployment:
			target.analyzer_deployment = deployment

		target.requested_by = frappe.session.user
		target.request_date = today()
		target.status = "Draft"

	return get_mapped_doc(
		"Instrument Placement Contract",
		source_name,
		{
			"Instrument Placement Contract": {
				"doctype": "Repossession Request",
				"field_map": {
					"name": "contract",
					"customer": "customer",
					"customer_name": "customer_name",
				},
				"validation": {
					"docstatus": ["=", 1],
				},
			},
		},
		target_doc,
		set_missing_values,
	)
