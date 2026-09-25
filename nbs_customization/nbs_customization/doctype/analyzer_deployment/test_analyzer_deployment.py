# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.tests.placement_contracts import make_contract_kit
from nbs_customization.tests.placement_fixtures import skip_test_record_bootstrap


class TestDeploymentSideEffects(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Analyzer Deployment")
		super().setUpClass()

	def test_deployed_sets_asset_status(self):
		ctx = make_contract_kit("_TST-DEP1")
		dep = frappe.get_doc(
			{
				"doctype": "Analyzer Deployment",
				"naming_series": "NBSAD-.YYYY./.####",
				"contract": ctx["contract"].name,
				"asset": ctx["asset"].name,
				"customer": ctx["customer"].name,
				"customer_site": ctx["site"].name,
				"asset_location": "Block 1",
				"asset_storage_location": "Field 1",
				"deployment_date": "2026-02-01",
				"deployment_status": "Under Service",
			}
		).insert()
		dep.deployment_status = "Deployed"
		dep.save()

		self.assertEqual(
			frappe.db.get_value("Asset", ctx["asset"].name, "custom_current_deployment_status"),
			"Deployed",
		)
		self.assertEqual(
			frappe.db.get_value("Asset", ctx["asset"].name, "custom_current_placement_contract"),
			ctx["contract"].name,
		)
		moves = frappe.db.get_all(
			"Asset Movement Item",
			filters={"asset": ctx["asset"].name},
			fields=["parent", "source_location", "target_location"],
		)
		deploy_moves = [m for m in moves if m.source_location == "Field 1" and m.target_location == "Block 1"]
		self.assertTrue(deploy_moves)
		move = frappe.get_doc("Asset Movement", deploy_moves[0].parent)
		self.assertEqual(move.docstatus, 1)
		self.assertEqual(move.purpose, "Transfer")

	def test_temporary_retrieval_keeps_contract_link(self):
		ctx = make_contract_kit("_TST-DEP2")
		dep = frappe.get_doc(
			{
				"doctype": "Analyzer Deployment",
				"naming_series": "NBSAD-.YYYY./.####",
				"contract": ctx["contract"].name,
				"asset": ctx["asset"].name,
				"customer": ctx["customer"].name,
				"customer_site": ctx["site"].name,
				"asset_location": "Block 1",
				"asset_storage_location": "Field 1",
				"deployment_date": "2026-02-01",
				"deployment_status": "Under Service",
			}
		).insert()
		dep.deployment_status = "Deployed"
		dep.save()
		dep.deployment_status = "Temporarily Retrieved"
		dep.save()

		self.assertEqual(
			frappe.db.get_value("Asset", ctx["asset"].name, "custom_current_deployment_status"),
			"Warehouse",
		)
		self.assertEqual(
			frappe.db.get_value("Asset", ctx["asset"].name, "custom_current_placement_contract"),
			ctx["contract"].name,
		)

	def test_permanent_retrieval_clears_contract(self):
		ctx = make_contract_kit("_TST-DEP3")
		before = frappe.db.count("Asset Movement", {"company": "NORTHLAND BIOMEDICAL SOLUTIONS"})
		dep = frappe.get_doc(
			{
				"doctype": "Analyzer Deployment",
				"naming_series": "NBSAD-.YYYY./.####",
				"contract": ctx["contract"].name,
				"asset": ctx["asset"].name,
				"customer": ctx["customer"].name,
				"customer_site": ctx["site"].name,
				"asset_location": "Block 1",
				"asset_storage_location": "Field 1",
				"deployment_date": "2026-02-01",
				"deployment_status": "Under Service",
			}
		).insert()
		dep.deployment_status = "Deployed"
		dep.save()
		dep.deployment_status = "Permanently Retrieved"
		dep.retrieval_date = frappe.utils.today()
		dep.save()

		self.assertEqual(
			frappe.db.get_value("Asset", ctx["asset"].name, "custom_current_deployment_status"),
			"Warehouse",
		)
		self.assertIsNone(
			frappe.db.get_value("Asset", ctx["asset"].name, "custom_current_placement_contract"),
		)
		after = frappe.db.count("Asset Movement", {"company": "NORTHLAND BIOMEDICAL SOLUTIONS"})
		self.assertGreaterEqual(after - before, 2)
