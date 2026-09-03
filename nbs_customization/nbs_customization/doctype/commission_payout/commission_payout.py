# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from nbs_customization.controllers.check_clearing import get_check_mop, validate_destination_account


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
		self._validate_check_or_bank_reference()

	def on_submit(self):
		self._update_parent_commission()

	def on_cancel(self):
		self._cancel_clearing_journal_entry()
		self._update_parent_commission()

	def _cancel_clearing_journal_entry(self):
		if not self.get("clearing_journal_entry"):
			return
		frappe.db.set_value(
			"Commission Payout", self.name, "clearing_journal_entry", None, update_modified=False
		)
		je_name = self.clearing_journal_entry
		if je_name and frappe.db.exists("Journal Entry", je_name):
			je = frappe.get_doc("Journal Entry", je_name)
			if je.docstatus == 1:
				je.cancel()

	def _validate_check_or_bank_reference(self):
		mop = get_check_mop(self.mode_of_payment) if self.mode_of_payment else {}
		needs_check = bool(mop.get("is_check"))
		if needs_check:
			self.is_check = 1
			expected = mop.get("clearing_account_outward")
			if expected and self.paid_from != expected:
				self.paid_from = expected
			if not self.clearing_destination_account and mop.get("default_clearing_destination"):
				self.clearing_destination_account = mop.get("default_clearing_destination")
		needs_bank = False
		if self.paid_from:
			account_type = frappe.get_cached_value("Account", self.paid_from, "account_type")
			if account_type == "Bank":
				needs_bank = True
		needs_ref = needs_check or needs_bank
		if needs_ref and (not self.reference_no or not self.reference_date):
			if needs_check:
				frappe.throw(_("Cheque/Reference No and Reference Date are mandatory for Check payments."))
			else:
				frappe.throw(_("Reference No and Reference Date is mandatory for Bank transaction"))

	def _validate_bank_reference(self):
		return self._validate_check_or_bank_reference()

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
		Credit: Paying Account (bank/cash or clearing outward for Check)
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
		je.mode_of_payment = self.mode_of_payment
		je.cheque_no = self.reference_no
		je.cheque_date = self.reference_date
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


def _is_bank_account(account):
	return frappe.get_cached_value("Account", account, "account_type") == "Bank"


def create_commission_check_clearing_je(payout, destination_account, clearing_date):
	"""Create clearing JE for a Check Commission Payout: Dr clearing / Cr Bank."""
	company_currency = frappe.get_cached_value("Company", payout.company, "default_currency")
	if payout.paid_from_account_currency != company_currency:
		frappe.throw(
			_(
				"Cheque clearing is only supported in company currency ({0}) for now. Commission Payout {1} is in a foreign currency."
			).format(company_currency, payout.name)
		)
	validate_destination_account(destination_account, payout.company)
	mop = get_check_mop(payout.mode_of_payment)
	clearing_account = payout.paid_from or mop.get("clearing_account_outward")
	if not clearing_account:
		frappe.throw(
			_("No clearing account configured for cheque Commission Payout {0}.").format(payout.name)
		)
	amount = payout.amount_to_pay
	is_bank_entry = bool(payout.reference_no and payout.reference_date)
	je = frappe.get_doc(
		doctype="Journal Entry",
		voucher_type="Bank Entry" if is_bank_entry else "Journal Entry",
		company=payout.company,
		posting_date=clearing_date,
		user_remark=_("Cheque clearing against {0}").format(payout.name),
	)
	if is_bank_entry:
		je.cheque_no = payout.reference_no
		je.cheque_date = payout.reference_date
	je.append(
		"accounts",
		{
			"account": clearing_account,
			"debit_in_account_currency": amount,
			"reference_type": "Commission Payout",
			"reference_name": payout.name,
			"cost_center": payout.cost_center,
		},
	)
	je.append(
		"accounts",
		{
			"account": destination_account,
			"credit_in_account_currency": amount,
			"reference_type": "Commission Payout",
			"reference_name": payout.name,
			"cost_center": payout.cost_center,
		},
	)
	je.insert(ignore_permissions=True)
	je.submit()
	return je.name


def stamp_commission_check_cleared(payout, je_name, clearing_date, source, destination_account):
	"""Conditional stamp of Commission Payout check flags. Returns rowcount."""
	clearance_date = clearing_date if _is_bank_account(destination_account) else None
	frappe.db.sql(
		"""
		update `tabCommission Payout`
		set is_check = %s,
			check_cleared = 1,
			check_clearing_date = %s,
			check_cleared_source = %s,
			clearing_destination_account = %s,
			clearing_journal_entry = %s,
			clearance_date = %s
		where name = %s and docstatus = 1 and ifnull(check_cleared, 0) = 0
		""",
		(
			payout.is_check or 1,
			clearing_date,
			source,
			destination_account,
			je_name,
			clearance_date,
			payout.name,
		),
	)
	cursor = getattr(frappe.db, "_cursor", None)
	return (cursor.rowcount if cursor else 0) or 0


@frappe.whitelist(methods=["POST"])
def mark_commission_check_cleared(name, destination_account=None, clearing_date=None, source="Button"):
	payout = frappe.get_doc("Commission Payout", name)
	if payout.docstatus != 1:
		frappe.throw(_("Only submitted Commission Payouts can be marked cleared."))
	if not payout.is_check:
		mop = get_check_mop(payout.mode_of_payment)
		if not mop.get("is_check"):
			frappe.throw(_("{0} is not a cheque Commission Payout.").format(payout.name))
	if payout.check_cleared or payout.check_returned:
		frappe.throw(_("{0} is already cleared or returned.").format(payout.name))
	mop = get_check_mop(payout.mode_of_payment)
	chosen = (
		destination_account or payout.clearing_destination_account or mop.get("default_clearing_destination")
	)
	if not chosen:
		chosen = frappe.get_cached_value("Company", payout.company, "default_bank_account")
	clear_date = clearing_date or today()
	je_name = create_commission_check_clearing_je(payout, chosen, clear_date)
	rows = stamp_commission_check_cleared(payout, je_name, clear_date, source, chosen)
	if rows != 1:
		frappe.get_doc("Journal Entry", je_name).cancel()
		frappe.throw(_("{0} was already cleared.").format(payout.name))
	return {"journal_entry": je_name, "cleared": True}


@frappe.whitelist(methods=["POST"])
def mark_commission_check_returned(name):
	payout = frappe.get_doc("Commission Payout", name)
	if payout.docstatus != 1:
		frappe.throw(_("Only submitted Commission Payouts can be marked returned."))
	if payout.check_returned:
		frappe.throw(_("{0} is already marked returned.").format(payout.name))
	if payout.clearing_journal_entry:
		frappe.db.set_value("Commission Payout", name, "clearing_journal_entry", None, update_modified=False)
		je_name = payout.clearing_journal_entry
		if je_name and frappe.db.exists("Journal Entry", je_name):
			je = frappe.get_doc("Journal Entry", je_name)
			if je.docstatus == 1:
				je.cancel()
	payout.cancel()
	frappe.db.set_value(
		"Commission Payout",
		name,
		{
			"check_returned": 1,
			"check_return_date": today(),
			"check_cleared": 0,
			"check_clearing_date": None,
			"check_cleared_source": None,
			"clearing_destination_account": None,
			"clearance_date": None,
		},
	)
	return {"returned": True}


@frappe.whitelist()
def get_payment_method_account(mode_of_payment, company):
	"""Resolves clearing-aware account for Commission Payout (mirror Expense)."""
	from nbs_customization.nbs_customization.doctype.expense.expense import (
		get_payment_method_account as _get_pma,
	)

	return _get_pma(mode_of_payment, company)


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
