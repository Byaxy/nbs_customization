import frappe
from frappe.tests import IntegrationTestCase

from nbs_customization.tasks import (
	daily_check_rlo_ownership,
	daily_process_amendments,
	monthly_generate_reconciliations,
	monthly_generate_revenue_share,
)
from nbs_customization.tests.placement_contracts import (
	make_contract_kit,
	make_si,
)
from nbs_customization.tests.placement_fixtures import ensure_stock


class TestTasks(IntegrationTestCase):
	def test_monthly_generate_reconciliations_imports(self):
		self.assertTrue(callable(monthly_generate_reconciliations))

	def test_monthly_generate_revenue_share_imports(self):
		self.assertTrue(callable(monthly_generate_revenue_share))

	def test_daily_process_amendments_imports(self):
		self.assertTrue(callable(daily_process_amendments))

	def test_daily_check_rlo_ownership_imports(self):
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

	def test_monthly_jobs_scope_by_contract_type(self):
		rra = make_contract_kit("_TST-TSK1")
		make_si(rra, 20, 200, "2026-07-10", "Contract Reagent Sale")
		cpt = make_contract_kit("_TST-TSK2", contract_type="CPT", agreed_price=600, share_pct=20)
		ensure_stock(cpt["reagent"].name, qty=50)
		period = frappe.utils.today()[:7]

		monthly_generate_reconciliations()
		self.assertTrue(
			frappe.db.exists(
				"Monthly Reconciliation",
				{"contract": rra["contract"].name, "period": period},
			)
		)
		self.assertFalse(
			frappe.db.exists(
				"Monthly Reconciliation",
				{"contract": cpt["contract"].name},
			)
		)

		monthly_generate_revenue_share()
		self.assertTrue(
			frappe.db.exists(
				"Revenue Share Statement",
				{"contract": cpt["contract"].name, "period": period},
			)
		)
		self.assertFalse(
			frappe.db.exists(
				"Revenue Share Statement",
				{"contract": rra["contract"].name},
			)
		)

	def test_daily_amendment_job_applies_due(self):
		ctx = make_contract_kit("_TST-TSK3")
		am = frappe.get_doc(
			{
				"doctype": "Contract Amendment",
				"contract": ctx["contract"].name,
				"amendment_date": frappe.utils.today(),
				"effective_date": frappe.utils.today(),
				"reason": "Pricing Adjustment",
				"new_declared_volume": 200,
				"status": "Approved",
			}
		).insert()
		daily_process_amendments()
		self.assertEqual(frappe.db.get_value("Contract Amendment", am.name, "status"), "Effective")

	def test_daily_rlo_check_creates_otr_once(self):
		ctx = make_contract_kit("_TST-TSK4", contract_type="RLO", target=12000)
		frappe.db.set_value(
			"Instrument Placement Contract",
			ctx["contract"].name,
			"ownership_threshold_met",
			1,
		)
		frappe.db.set_value(
			"Instrument Placement Contract",
			ctx["contract"].name,
			"outstanding_on_contract",
			0,
		)
		daily_check_rlo_ownership()
		first = frappe.db.get_value(
			"Ownership Transfer Request",
			{"contract": ctx["contract"].name},
			"name",
		)
		self.assertTrue(first)
		daily_check_rlo_ownership()
		self.assertEqual(
			frappe.db.count("Ownership Transfer Request", {"contract": ctx["contract"].name}),
			1,
		)
		ctx2 = make_contract_kit("_TST-TSK5", contract_type="RLO", target=12000)
		daily_check_rlo_ownership()
		self.assertFalse(
			frappe.db.exists(
				"Ownership Transfer Request",
				{"contract": ctx2["contract"].name},
			)
		)

	def test_monthly_job_isolates_failures(self):
		good = make_contract_kit("_TST-TSK6")
		bad = make_contract_kit("_TST-TSK7")
		period = frappe.utils.today()[:7]
		import nbs_customization.tasks as tasks_mod

		real = tasks_mod.generate_monthly_reconciliation

		def flaky(contract_name, period_arg):
			if contract_name == bad["contract"].name:
				raise frappe.ValidationError("simulated bad contract")
			return real(contract_name, period_arg)

		tasks_mod.generate_monthly_reconciliation = flaky
		try:
			monthly_generate_reconciliations()
		finally:
			tasks_mod.generate_monthly_reconciliation = real
		self.assertTrue(
			frappe.db.exists(
				"Monthly Reconciliation",
				{"contract": good["contract"].name, "period": period},
			)
		)
		self.assertTrue(
			frappe.db.exists(
				"Error Log",
				{"method": ("like", "%Monthly Reconciliation Generation Failed%")},
			)
		)
