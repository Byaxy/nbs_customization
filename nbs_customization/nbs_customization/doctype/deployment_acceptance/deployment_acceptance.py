# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from nbs_customization.utils.placement.dates import validate_not_future


class DeploymentAcceptance(Document):
	def validate(self):
		validate_not_future(self.acceptance_date, _("Acceptance Date"))
		deployment = self._get_deployment()
		self.contract = deployment.contract
		self.asset = deployment.asset
		self.serial_no = deployment.serial_no
		self.customer = deployment.customer
		self.customer_site = deployment.customer_site
		self._validate_status(deployment)
		self._validate_duplicate(deployment)

	def before_submit(self):
		if not self.customer_signed:
			frappe.throw(_("Customer Signed must be checked before submitting acceptance."))

	def on_submit(self):
		frappe.db.set_value(
			"Analyzer Deployment",
			self.deployment,
			{
				"acceptance_document": self.name,
				"acceptance_signed": 1,
				"acceptance_date": self.acceptance_date,
			},
		)

	def on_cancel(self):
		_clear_deployment_acceptance(self.deployment, self.name)

	def on_trash(self):
		_clear_deployment_acceptance(self.deployment, self.name)

	def _get_deployment(self):
		if not self.deployment:
			frappe.throw(_("Analyzer Deployment is required."))
		return frappe.get_doc("Analyzer Deployment", self.deployment)

	def _validate_status(self, deployment):
		if deployment.deployment_status not in ("Deployed", "Under Service"):
			frappe.throw(
				_("Acceptance requires a Deployed or Under Service deployment (current: {0}).").format(
					frappe.bold(deployment.deployment_status)
				)
			)

	def _validate_duplicate(self, deployment):
		existing = frappe.db.get_value(
			"Deployment Acceptance",
			{
				"deployment": deployment.name,
				"docstatus": 1,
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Deployment {0} already has submitted acceptance {1}.").format(
					frappe.bold(deployment.name), frappe.bold(existing)
				)
			)


def _clear_deployment_acceptance(deployment, acceptance_name):
	if not deployment or not acceptance_name:
		return
	linked = frappe.db.get_value("Analyzer Deployment", deployment, "acceptance_document")
	if linked != acceptance_name:
		return
	frappe.db.set_value(
		"Analyzer Deployment",
		deployment,
		{
			"acceptance_document": None,
			"acceptance_signed": 0,
			"acceptance_date": None,
		},
	)
