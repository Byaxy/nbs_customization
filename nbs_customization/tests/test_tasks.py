import frappe
import frappe.tests
from frappe.tests.utils import FrappeTestCase


class TestTasks(FrappeTestCase):
	def test_monthly_generate_reconciliations_imports(self):
		from nbs_customization.tasks import monthly_generate_reconciliations
		self.assertTrue(callable(monthly_generate_reconciliations))

	def test_monthly_generate_revenue_share_imports(self):
		from nbs_customization.tasks import monthly_generate_revenue_share
		self.assertTrue(callable(monthly_generate_revenue_share))

	def test_daily_process_amendments_imports(self):
		from nbs_customization.tasks import daily_process_amendments
		self.assertTrue(callable(daily_process_amendments))

	def test_daily_check_rlo_ownership_imports(self):
		from nbs_customization.tasks import daily_check_rlo_ownership
		self.assertTrue(callable(daily_check_rlo_ownership))

	def test_apply_amendment_to_contract_imports(self):
		from nbs_customization.tasks import _apply_amendment_to_contract
		self.assertTrue(callable(_apply_amendment_to_contract))

	def test_create_ownership_transfer_request_imports(self):
		from nbs_customization.nbs_customization.doctype.ownership_transfer_request.ownership_transfer_request import (
			create_ownership_transfer_request,
		)
		self.assertTrue(callable(create_ownership_transfer_request))

	def test_create_penalty_invoice_imports(self):
		from nbs_customization.nbs_customization.doctype.monthly_reconciliation.monthly_reconciliation import (
			create_penalty_invoice,
		)
		self.assertTrue(callable(create_penalty_invoice))

	def test_make_deployment_imports(self):
		from nbs_customization.controllers.placement.contract import make_deployment
		self.assertTrue(callable(make_deployment))

	def test_make_repossession_request_imports(self):
		from nbs_customization.controllers.placement.contract import make_repossession_request
		self.assertTrue(callable(make_repossession_request))

	def test_mark_effective_imports(self):
		from nbs_customization.controllers.placement.amendment import mark_effective
		self.assertTrue(callable(mark_effective))
