# Copyright (c) 2026, Charles Byakutaga/NBS and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, getdate

from nbs_customization.nbs_customization.page.daily_income_expense.daily_income_expense import (
	get_data,
)
from nbs_customization.nbs_customization.report.daily_income_and_expense.daily_income_and_expense import (
	execute as run_daily_report,
)


class IntegrationTestDailyIncomeAndExpense(IntegrationTestCase):
	COMPANY = "_Test Company"
	BANK = "_Test Bank - _TC"
	CASH = "_Test Cash - _TC"
	EXPENSE_ACCOUNT = "Loyalty - _TC"
	EQUITY = "Opening Balance Equity - _TC"
	REPORT_DATE = getdate("2026-01-15")

	# ------------------------------------------------------------------ #
	# Fixtures                                                            #
	# ------------------------------------------------------------------ #

	def _seed_bank(self, amount=10000):
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.COMPANY
		je.posting_date = add_days(self.REPORT_DATE, -1)
		je.user_remark = "seed bank balance for Daily Income and Expense tests"
		je.append(
			"accounts",
			{
				"account": self.EQUITY,
				"debit_in_account_currency": amount,
				"credit_in_account_currency": 0,
			},
		)
		je.append(
			"accounts",
			{
				"account": self.BANK,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": amount,
			},
		)
		je.insert(ignore_permissions=True)
		je.submit()
		return je

	def _expense_category(self):
		name = "Test Expense Category"
		if not frappe.db.exists("Expense Category", name):
			doc = frappe.new_doc("Expense Category")
			doc.name = name
			doc.category_name = name
			doc.expense_account = self.EXPENSE_ACCOUNT
			doc.insert(ignore_permissions=True)
		return name

	def _direct_expense(self, amount=100):
		doc = frappe.new_doc("Expense")
		doc.update(
			{
				"company": self.COMPANY,
				"expense_date": self.REPORT_DATE,
				"expense_description": "Test Direct Expense",
				"amount": amount,
				"payee": "Test Payee",
				"expense_category": self._expense_category(),
				"payment_type": "Direct Payment",
				"mode_of_payment": "Wire Transfer",
				"paid_from": self.CASH,
			}
		)
		doc.insert()
		doc.submit()
		return doc

	def _against_pi_expense(self, pi, amount=150):
		doc = frappe.new_doc("Expense")
		doc.update(
			{
				"company": self.COMPANY,
				"expense_date": self.REPORT_DATE,
				"expense_description": "Test Invoice Payment",
				"amount": amount,
				"payee": "_Test Supplier",
				"payment_type": "Against Purchase Invoice",
				"purchase_invoice": pi.name,
				"mode_of_payment": "Wire Transfer",
				"paid_from": self.BANK,
				"reference_no": "BANK-TRF-001",
				"reference_date": self.REPORT_DATE,
			}
		)
		doc.insert()
		doc.submit()
		return doc

	def _receive_pe(self, si):
		from erpnext.accounts.doctype.payment_entry.payment_entry import (
			get_payment_entry,
		)

		pe = get_payment_entry("Sales Invoice", si.name)
		pe.posting_date = self.REPORT_DATE
		pe.paid_to = self.BANK
		pe.mode_of_payment = "Wire Transfer"
		pe.reference_no = "BANK-RCV-001"
		pe.reference_date = self.REPORT_DATE
		pe.insert(ignore_permissions=True)
		pe.submit()
		return pe

	def _commission_payout(self, si, amount=90.09):
		sales_person = "Test Sales Person"
		if not frappe.db.exists("Sales Person", sales_person):
			frappe.get_doc(
				{
					"doctype": "Sales Person",
					"sales_person_name": sales_person,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

		sc = frappe.new_doc("Sales Commission")
		sc.company = self.COMPANY
		sc.customer = si.customer
		sc.commission_date = self.REPORT_DATE
		sc.append("commission_sales", {"sale": si.name, "commission_rate": 100})
		sc.append(
			"commission_recipients",
			{"sales_person": sales_person, "allocated_amount": flt(si.grand_total)},
		)
		sc.insert(ignore_permissions=True)
		sc.submit()

		cp = frappe.new_doc("Commission Payout")
		cp.update(
			{
				"company": self.COMPANY,
				"commission": sc.name,
				"commission_recipient": sc.commission_recipients[0].name,
				"payout_date": self.REPORT_DATE,
				"amount_to_pay": amount,
				"expense_category": self._expense_category(),
				"mode_of_payment": "Wire Transfer",
				"paid_from": self.BANK,
			}
		)
		cp.insert(ignore_permissions=True)
		cp.submit()
		cp.reload()
		return cp, sc

	def _run(self):
		_columns, data = run_daily_report({"company": self.COMPANY, "report_date": self.REPORT_DATE})
		return data

	def _row(self, data, account):
		rows = [r for r in data if r.get("account") == account]
		self.assertEqual(len(rows), 1, f"expected exactly one row for {account}, got {rows}")
		return rows[0]

	def _detail(self, data, voucher_no):
		return [r for r in data if r.get("voucher_no") == voucher_no]

	# ------------------------------------------------------------------ #
	# Tests                                                               #
	# ------------------------------------------------------------------ #

	def test_report_balances_and_pnl(self):
		from erpnext.accounts.doctype.purchase_invoice.test_purchase_invoice import (
			make_purchase_invoice,
		)
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import (
			create_sales_invoice,
		)

		seed = self._seed_bank()
		baseline = self._run()

		si = create_sales_invoice(posting_date=self.REPORT_DATE, rate=100, qty=1)
		received = self._receive_pe(si)
		direct = self._direct_expense()
		pi = make_purchase_invoice()
		against = self._against_pi_expense(pi)
		commission_payout, commission = self._commission_payout(si)

		after = self._run()

		try:
			# ---- Cash & Bank: carried forward = brought forward + day ----
			bank = self._row(after, self.BANK)
			self.assertAlmostEqual(flt(bank["day_movement"]), -140.09, places=2)
			self.assertEqual(
				flt(bank["carried_forward"]), flt(bank["brought_forward"]) + flt(bank["day_movement"])
			)

			cash = self._row(after, self.CASH)
			self.assertEqual(flt(cash["day_movement"]), -100)
			self.assertEqual(flt(cash["carried_forward"]), flt(cash["brought_forward"]) - 100)

			# Baseline had no movement yet — brought forward matches its carried forward
			base_bank = self._row(baseline, self.BANK)
			self.assertEqual(flt(bank["brought_forward"]), flt(base_bank["carried_forward"]))

			# ---- Income (cash received = Payment Entries) ----
			base_income = self._row(baseline, "Total Income")
			income_total = self._row(after, "Total Income")
			self.assertEqual(flt(base_income["day_movement"]), 0)
			self.assertEqual(flt(income_total["day_movement"]), 100)

			income_rows = self._detail(after, received.name)
			self.assertEqual(len(income_rows), 1)
			income_row = income_rows[0]
			self.assertEqual(income_row["type"], "Payment Entry")
			self.assertEqual(flt(income_row["day_movement"]), 100)
			self.assertEqual(income_row["party"], received.party_name)
			self.assertEqual(income_row["linked_invoice"], si.name)

			# ---- Expenses: direct expense (JE) + invoice payment (PE) + commission payout ----
			loyalty_rows = self._detail(after, direct.journal_entry)
			self.assertEqual(len(loyalty_rows), 1)
			self.assertEqual(flt(loyalty_rows[0]["day_movement"]), 100)
			self.assertEqual(loyalty_rows[0]["type"], "Journal Entry")
			self.assertEqual(loyalty_rows[0]["party"], "Test Payee")
			self.assertEqual(loyalty_rows[0]["linked_invoice"], direct.name)

			creditor_rows = self._detail(after, against.payment_entry)
			self.assertEqual(len(creditor_rows), 1)
			self.assertEqual(flt(creditor_rows[0]["day_movement"]), 150)
			self.assertEqual(creditor_rows[0]["type"], "Payment Entry")
			self.assertEqual(creditor_rows[0]["party"], "_Test Supplier")
			self.assertEqual(creditor_rows[0]["linked_invoice"], pi.name)

			commission_rows = self._detail(after, commission_payout.journal_entry)
			self.assertEqual(len(commission_rows), 1)
			commission_row = commission_rows[0]
			self.assertEqual(commission_row["voucher_type"], "Journal Entry")
			self.assertEqual(commission_row["type"], "Commission Payout")
			self.assertAlmostEqual(flt(commission_row["day_movement"]), 90.09, places=2)
			self.assertEqual(commission_row["party"], "Test Sales Person")
			self.assertEqual(commission_row["mode_of_payment"], "Wire Transfer")
			self.assertEqual(commission_row["linked_invoice"], commission_payout.name)

			base_expense = self._row(baseline, "Total Expenses")
			expense_total = self._row(after, "Total Expenses")
			self.assertEqual(flt(base_expense["day_movement"]), 0)
			self.assertAlmostEqual(flt(expense_total["day_movement"]), 340.09, places=2)

			# ---- Net income (loss) ----
			net = self._row(after, "Net Income (Loss)")
			self.assertAlmostEqual(
				flt(net["day_movement"]),
				flt(income_total["day_movement"]) - flt(expense_total["day_movement"]),
				places=2,
			)
		finally:
			received.cancel()
			against.cancel()
			pi.reload()
			if pi.docstatus == 1:
				pi.cancel()
			frappe.delete_doc("Purchase Invoice", pi.name, force=True)
			direct.cancel()
			commission_payout.cancel()
			commission.cancel()
			si.reload()
			if si.docstatus == 1:
				si.cancel()
			seed.cancel()

	def test_dashboard_get_data(self):
		from erpnext.accounts.doctype.purchase_invoice.test_purchase_invoice import (
			make_purchase_invoice,
		)
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import (
			create_sales_invoice,
		)

		seed = self._seed_bank()

		try:
			si = create_sales_invoice(posting_date=self.REPORT_DATE, rate=100, qty=1)
			received = self._receive_pe(si)
			direct = self._direct_expense()
			pi = make_purchase_invoice()
			against = self._against_pi_expense(pi)
			commission_payout, commission = self._commission_payout(si)

			payload = get_data(company=self.COMPANY, report_date=str(self.REPORT_DATE))

			self.assertEqual(payload["company"], self.COMPANY)
			self.assertEqual(payload["report_date"], str(self.REPORT_DATE))

			# ---- Cash & Bank accounts ----
			bank = next(a for a in payload["accounts"] if a["account"] == self.BANK)
			self.assertAlmostEqual(flt(bank["day_movement"]), -140.09, places=2)
			self.assertEqual(
				flt(bank["carried_forward"]), flt(bank["brought_forward"]) + flt(bank["day_movement"])
			)

			cash = next(a for a in payload["accounts"] if a["account"] == self.CASH)
			self.assertEqual(flt(cash["day_movement"]), -100)
			self.assertEqual(
				flt(cash["carried_forward"]), flt(cash["brought_forward"]) + flt(cash["day_movement"])
			)

			# ---- Totals ----
			self.assertAlmostEqual(flt(payload["cash_bank_total"]["day_movement"]), -240.09, places=2)
			self.assertEqual(
				flt(payload["cash_bank_total"]["carried_forward"]),
				flt(payload["cash_bank_total"]["brought_forward"])
				+ flt(payload["cash_bank_total"]["day_movement"]),
			)

			self.assertEqual(flt(payload["income"]["total"]), 100)
			self.assertAlmostEqual(flt(payload["expenses"]["total"]), 340.09, places=2)
			self.assertAlmostEqual(flt(payload["net"]), -240.09, places=2)

			# ---- Detail rows match the Report's output ----
			report_data = self._run()
			income_rows = payload["income"]["rows"]
			expense_rows = payload["expenses"]["rows"]
			self.assertEqual(len(income_rows), 1)
			self.assertEqual(income_rows[0]["voucher_no"], received.name)
			self.assertEqual(income_rows[0]["type"], "Payment Entry")
			self.assertEqual(flt(income_rows[0]["amount"]), 100)
			self.assertEqual(income_rows[0]["linked_invoice"], si.name)
			self.assertEqual(len(expense_rows), 3)

			commission_row = next(
				r for r in expense_rows if r["voucher_no"] == commission_payout.journal_entry
			)
			self.assertEqual(commission_row["voucher_type"], "Journal Entry")
			self.assertEqual(commission_row["type"], "Commission Payout")
			self.assertEqual(commission_row["party"], "Test Sales Person")
			self.assertEqual(commission_row["mode_of_payment"], "Wire Transfer")
			self.assertEqual(commission_row["linked_invoice"], commission_payout.name)
			self.assertAlmostEqual(flt(commission_row["amount"]), 90.09, places=2)

			report_income = [r for r in report_data if r.get("voucher_no") == received.name]
			self.assertEqual(len(report_income), 1)
			self.assertEqual(income_rows[0]["voucher_no"], report_income[0]["voucher_no"])
		finally:
			received.cancel()
			against.cancel()
			pi.reload()
			if pi.docstatus == 1:
				pi.cancel()
			frappe.delete_doc("Purchase Invoice", pi.name, force=True)
			direct.cancel()
			commission_payout.cancel()
			commission.cancel()
			si.reload()
			if si.docstatus == 1:
				si.cancel()
			seed.cancel()
