# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.tests import IntegrationTestCase

from nbs_customization.controllers.placement.sales_validate import _validate_contract_rates
from nbs_customization.tests.placement_contracts import make_contract_kit, make_payment, make_si
from nbs_customization.tests.placement_fixtures import COMPANY, skip_test_record_bootstrap


class TestPlacementSalesValidation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		skip_test_record_bootstrap("Sales Invoice")
		super().setUpClass()

	def _fulfilled_contract(self, prefix):
		ctx = make_contract_kit(prefix, target=12000)
		si = make_si(ctx, 60, 200, "2026-07-10", "Contract Reagent Sale")
		make_payment(si)
		contract = frappe.get_doc("Instrument Placement Contract", ctx["contract"].name)
		self.assertEqual(contract.contract_status, "Fulfilled")
		return ctx, si

	def test_return_against_fulfilled_contract_allowed(self):
		ctx, si = self._fulfilled_contract("_TST-SV1")
		ret = make_return_doc("Sales Invoice", si.name)
		ret.insert()
		ret.submit()
		self.assertEqual(ret.docstatus, 1)
		self.assertEqual(ret.custom_instrument_placement_contract, ctx["contract"].name)

	def test_new_sale_against_fulfilled_contract_blocked(self):
		ctx, _si = self._fulfilled_contract("_TST-SV2")
		with self.assertRaises(frappe.ValidationError):
			make_si(ctx, 10, 200, "2026-07-12", "Contract Reagent Sale")

	def test_rate_comparison_converts_to_company_currency(self):
		doc = frappe._dict(
			company=COMPANY,
			conversion_rate=1.2,
			posting_date="2026-07-10",
			items=[
				frappe._dict(
					item_code="_TST-RATE-ITEM",
					rate=45,
					base_rate=54,
					conversion_factor=1,
				)
			],
		)
		contract = frappe._dict(
			company=COMPANY,
			contract_price_list=None,
			contract_reagent_lines=[
				frappe._dict(item_code="_TST-RATE-ITEM", contract_price=50),
			],
		)
		_validate_contract_rates(doc, contract, "Contract Reagent Sale")

	def test_return_skips_contract_rate_floor(self):
		doc = frappe._dict(
			is_return=1,
			company=COMPANY,
			conversion_rate=1,
			items=[frappe._dict(item_code="_TST-RATE-ITEM", rate=1, base_rate=1)],
		)
		contract = frappe._dict(
			company=COMPANY,
			contract_price_list=None,
			contract_reagent_lines=[frappe._dict(item_code="_TST-RATE-ITEM", contract_price=50)],
		)
		_validate_contract_rates(doc, contract, "Contract Reagent Sale")
