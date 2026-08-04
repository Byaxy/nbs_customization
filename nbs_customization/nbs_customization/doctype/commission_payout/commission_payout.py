# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CommissionPayout(Document):
	# ------------------------------------------------------------------ #
	#  Lifecycle hooks                                                     #
	# ------------------------------------------------------------------ #

	def validate(self):
		self._set_company_defaults()
		self._resolve_payment_account()
		self._resolve_paid_to()
		self._set_account_currencies()
		self.validate_commission_is_submitted()
		self.validate_recipient_belongs_to_commission()
		self.validate_recipient_not_fully_paid()
		self.validate_amount()
		self.validate_paid_from()
		self.validate_expense_category_not_accompanying()

	def on_submit(self):
		self._update_parent_commission()

	def on_cancel(self):
		self._update_parent_commission()

	# ------------------------------------------------------------------ #
	#  Validation helpers                                                  #
	# ------------------------------------------------------------------ #

	def _set_company_defaults(self):
		if not self.company:
			self.company = frappe.defaults.get_user_default("Company")
		if not self.cost_center:
			self.cost_center = frappe.db.get_value("Company", self.company, "cost_center")

	def _resolve_payment_account(self):
		"""
		Resolve the paying account from the Payment Method, mirroring Payment Entry.
		A manual override of paid_from is respected.
		"""
		if not self.mode_of_payment:
			# Legacy fallback: old drafts without a payment method
			if self.paying_account and not self.paid_from:
				self.paid_from = self.paying_account
			return

		if not self.paid_from:
			from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
				get_bank_cash_account,
			)

			self.paid_from = get_bank_cash_account(self.mode_of_payment, self.company)["account"]

	def _resolve_paid_to(self):
		"""Sets the read-only 'paid to' account to the category's expense account (JE debit side)."""
		self.paid_to = frappe.db.get_value("Expense Category", self.expense_category, "expense_account")

	def _set_account_currencies(self):
		self.paid_from_account_currency = (
			frappe.db.get_value("Account", self.paid_from, "account_currency") if self.paid_from else None
		)
		self.paid_to_account_currency = (
			frappe.db.get_value("Account", self.paid_to, "account_currency") if self.paid_to else None
		)

	def validate_commission_is_submitted(self):
		if not self.commission:
			return
		status = frappe.db.get_value("Sales Commission", self.commission, "docstatus")
		if status != 1:
			frappe.throw(
				_("Commission <b>{0}</b> must be approved (submitted) before processing a payout.").format(
					self.commission
				),
				title=_("Commission Not Approved"),
			)

	def validate_recipient_belongs_to_commission(self):
		if not self.commission_recipient or not self.commission:
			return
		parent = frappe.db.get_value("Commission Recipient", self.commission_recipient, "parent")
		if parent != self.commission:
			frappe.throw(
				_("Commission Recipient <b>{0}</b> does not belong to Commission <b>{1}</b>.").format(
					self.commission_recipient, self.commission
				),
				title=_("Invalid Recipient"),
			)

	def validate_recipient_not_fully_paid(self):
		if not self.commission_recipient:
			return
		status = frappe.db.get_value("Commission Recipient", self.commission_recipient, "payment_status")
		if status == "Paid":
			frappe.throw(
				_(
					"This recipient has already been fully paid. "
					"No further payouts are allowed for this recipient."
				),
				title=_("Already Fully Paid"),
			)
		if status == "Cancelled":
			frappe.throw(
				_("This recipient has been cancelled and cannot receive a payout."),
				title=_("Recipient Cancelled"),
			)

	def validate_amount(self):
		if not self.commission_recipient:
			return

		amount_to_pay = flt(self.amount_to_pay)
		if amount_to_pay <= 0:
			frappe.throw(
				_("Amount To Pay must be greater than zero."),
				title=_("Invalid Amount"),
			)

		recipient_row = frappe.db.get_value(
			"Commission Recipient",
			self.commission_recipient,
			["allocated_amount", "paid_amount"],
			as_dict=True,
		)
		if not recipient_row:
			return

		allocated = flt(recipient_row.allocated_amount)
		paid_so_far = flt(recipient_row.paid_amount)

		# If we're editing a submitted payout (amend), exclude this payout's own amount
		if not self.is_new() and self.docstatus == 1:
			paid_so_far = max(0.0, paid_so_far - amount_to_pay)

		remaining = flt(allocated - paid_so_far, 2)

		if amount_to_pay > remaining + 0.01:
			frappe.throw(
				_("Amount To Pay ({0}) exceeds the Remaining Due ({1}) for this recipient.").format(
					frappe.format_value(amount_to_pay, {"fieldtype": "Currency"}),
					frappe.format_value(remaining, {"fieldtype": "Currency"}),
				),
				title=_("Amount Exceeds Remaining Due"),
			)

	def validate_paid_from(self):
		if not self.paid_from:
			return

		account = frappe.db.get_value(
			"Account",
			self.paid_from,
			["account_type", "is_group", "disabled"],
			as_dict=True,
		)
		if not account:
			frappe.throw(
				_("Account Paid From <b>{0}</b> not found.").format(self.paid_from),
				title=_("Invalid Account"),
			)
		if account.is_group:
			frappe.throw(
				_(
					"Account Paid From <b>{0}</b> is a group account and cannot be used for transactions."
				).format(self.paid_from),
				title=_("Group Account Not Allowed"),
			)
		if account.disabled:
			frappe.throw(
				_("Account Paid From <b>{0}</b> is disabled.").format(self.paid_from),
				title=_("Disabled Account"),
			)

	def validate_expense_category_not_accompanying(self):
		"""Ensure selected expense category is not marked as accompanying expense."""
		if not self.expense_category:
			return
		is_accompanying = frappe.db.get_value(
			"Expense Category", self.expense_category, "is_accompanying_expense"
		)
		if is_accompanying:
			frappe.throw(_(f"Expense Category {self.expense_category} cannot be an accompanying expense."))

	# ------------------------------------------------------------------ #
	#  Post-submit / cancel: Journal Entry + status sync                  #
	# ------------------------------------------------------------------ #

	def _update_parent_commission(self):
		"""
		After submit or cancel:
		   1. Create or reverse the Journal Entry.
		   2. Tell the parent Sales Commission to recompute recipient fields
		      (paid_amount, remaining_due, payment_status) and its own
		      payment_status — all from a fresh DB query so the numbers
		      are always authoritative regardless of order of operations.
		"""
		if self.docstatus == 1:
			self._create_journal_entry()
		elif self.docstatus == 2:
			self._cancel_journal_entry()

		# Recompute overall commission status
		commission_doc = frappe.get_doc("Sales Commission", self.commission)
		commission_doc.recompute_payment_status()

	def _create_journal_entry(self):
		"""
		Debit: Expense Category's linked account (commission expense going out)
		Credit: Paying Account (bank/cash going out)
		"""
		expense_account = frappe.db.get_value("Expense Category", self.expense_category, "expense_account")
		if not expense_account:
			frappe.throw(
				_(
					"Expense Category <b>{0}</b> does not have a linked Account. "
					"Please configure it before processing payouts."
				).format(self.expense_category),
				title=_("Account Not Configured"),
			)

		sales_person_name = frappe.db.get_value(
			"Commission Recipient", self.commission_recipient, "sales_person"
		)

		remark = _("Commission Payout: {0} from {1} | Ref Commission: {2} | Payout Ref: {3}").format(
			sales_person_name or self.commission_recipient,
			self.paid_from,
			self.commission,
			self.name,
		)

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.payout_date
		je.user_remark = remark
		# No reference_doctype/reference_name - not allowed for JE rows in v16

		# Debit: commission expense account
		je.append(
			"accounts",
			{
				"account": expense_account,
				"debit_in_account_currency": flt(self.amount_to_pay),
				"credit_in_account_currency": 0,
				"cost_center": frappe.db.get_value("Company", self.company, "cost_center"),
				"user_remark": _("Commission expense for {0}").format(
					sales_person_name or self.commission_recipient
				),
			},
		)

		# Credit: paying account (bank/cash)
		je.append(
			"accounts",
			{
				"account": self.paid_from,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": flt(self.amount_to_pay),
				"user_remark": _("Commission payment from {0}").format(self.paid_from),
			},
		)

		je.flags.ignore_permissions = True
		je.insert()
		je.submit()

		# Store reference to the journal entry on this payout
		frappe.db.set_value("Commission Payout", self.name, "journal_entry", je.name)
		self.journal_entry = je.name

	def _cancel_journal_entry(self):
		"""Cancel the linked Journal Entry when a payout is cancelled."""
		je_name = frappe.db.get_value("Commission Payout", self.name, "journal_entry")
		if je_name:
			je_doc = frappe.get_doc("Journal Entry", je_name)
			if je_doc.docstatus == 1:
				je_doc.flags.ignore_permissions = True
				je_doc.cancel()


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def commission_recipient_query(doctype, txt, searchfield, start, page_len, filters):
	commission = (filters or {}).get("commission")
	if not commission:
		return []

	txt = f"%{txt}%"

	return frappe.db.sql(
		"""
        SELECT
            cr.name,
            cr.sales_person,
            cr.allocated_amount
        FROM `tabCommission Recipient` cr
        WHERE cr.parent = %(commission)s
          AND cr.parenttype = 'Sales Commission'
          AND cr.docstatus < 2
          AND cr.payment_status NOT IN ('Paid', 'Cancelled')
          AND (
                cr.name LIKE %(txt)s
             OR cr.sales_person LIKE %(txt)s
          )
        ORDER BY cr.sales_person ASC
        LIMIT %(start)s, %(page_len)s
        """,
		{
			"commission": commission,
			"txt": txt,
			"start": start,
			"page_len": page_len,
		},
	)


@frappe.whitelist()
def get_recipient_summary(recipient):
	doc = frappe.get_doc("Commission Recipient", recipient)

	# Ensure accurate computed values
	allocated = doc.allocated_amount or 0
	paid = doc.paid_amount or 0
	remaining = allocated - paid

	# Normalize status
	if remaining <= 0:
		status = "Paid"
	elif paid > 0:
		status = "Partial"
	else:
		status = "Pending"

	return {
		"sales_person": doc.sales_person,
		"allocated_amount": allocated,
		"paid_amount": paid,
		"remaining_due": remaining,
		"payment_status": status,
	}
