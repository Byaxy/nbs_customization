import frappe
from frappe.utils import today

from nbs_customization.utils.placement.permissions import (
	PLACEMENT_MANAGERS,
	STOCK_MANAGERS,
	require_contract_access,
	require_roles,
)


@frappe.whitelist()
def make_deployment(source_name, target_doc=None):
	from frappe.model.mapper import get_mapped_doc

	require_roles(*STOCK_MANAGERS)
	require_contract_access(source_name, "write")
	contract = frappe.get_doc("Instrument Placement Contract", source_name)
	if contract.contract_status != "Active":
		frappe.throw(
			frappe._("Contract {0} must be Active before deployment.").format(frappe.bold(source_name))
		)
	if frappe.db.exists(
		"Analyzer Deployment",
		{
			"contract": source_name,
			"deployment_status": ("in", ("Deployed", "Under Service", "Temporarily Retrieved")),
		},
	):
		frappe.throw(
			frappe._("Contract {0} already has an active deployment.").format(frappe.bold(source_name))
		)

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

	require_roles(*STOCK_MANAGERS)
	if frappe.db.get_value(
		"Analyzer Deployment",
		{"asset": asset_name, "deployment_status": ("in", ("Deployed", "Under Service"))},
		"name",
	):
		frappe.throw(
			frappe._("Asset {0} has a Deployed deployment — retrieve it before decommissioning.").format(
				asset_name
			)
		)
	contract = frappe.db.get_value("Asset", asset_name, "custom_current_placement_contract")
	if contract:
		status = frappe.db.get_value("Instrument Placement Contract", contract, "contract_status")
		if status in ("Active", "Ownership Pending"):
			frappe.throw(
				frappe._("Asset {0} is linked to open contract {1} — close it first.").format(
					asset_name, contract
				)
			)
	scrap_asset(asset_name)
	return asset_name


@frappe.whitelist()
def make_repossession_request(source_name, target_doc=None):
	from frappe.model.mapper import get_mapped_doc

	require_roles(*PLACEMENT_MANAGERS)
	require_contract_access(source_name, "write")
	contract = frappe.get_doc("Instrument Placement Contract", source_name)
	if contract.contract_status not in ("Active", "Ownership Pending"):
		frappe.throw(frappe._("Contract {0} is not open for repossession.").format(frappe.bold(source_name)))
	if frappe.db.exists(
		"Repossession Request",
		{"contract": source_name, "status": ("not in", ("Analyzer Retrieved", "Closed"))},
	):
		frappe.throw(
			frappe._("Contract {0} already has an open Repossession Request.").format(
				frappe.bold(source_name)
			)
		)

	def set_missing_values(source, target):
		deployment = frappe.db.get_value(
			"Analyzer Deployment",
			{"contract": source.name, "deployment_status": ("in", ("Deployed", "Under Service"))},
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
					"contract_type": "contract_type",
					"asset": "asset",
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
