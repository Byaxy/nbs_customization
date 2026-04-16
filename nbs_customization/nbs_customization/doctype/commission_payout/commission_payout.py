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
        self.validate_commission_is_submitted()
        self.validate_recipient_belongs_to_commission()
        self.validate_recipient_not_fully_paid()
        self.validate_amount()
        self.validate_paying_account()

    def on_submit(self):
        self._update_parent_commission()

    def on_cancel(self):
        self._update_parent_commission()

    # ------------------------------------------------------------------ #
    #  Validation helpers                                                  #
    # ------------------------------------------------------------------ #

    def validate_commission_is_submitted(self):
        if not self.commission:
            return
        status = frappe.db.get_value("Sales Commission", self.commission, "docstatus")
        if status != 1:
            frappe.throw(
                _(
                    "Commission <b>{0}</b> must be approved (submitted) before processing a payout."
                ).format(self.commission),
                title=_("Commission Not Approved"),
            )

    def validate_recipient_belongs_to_commission(self):
        if not self.commission_recipient or not self.commission:
            return
        parent = frappe.db.get_value(
            "Commission Recipient", self.commission_recipient, "parent"
        )
        if parent != self.commission:
            frappe.throw(
                _(
                    "Commission Recipient <b>{0}</b> does not belong to Commission <b>{1}</b>."
                ).format(self.commission_recipient, self.commission),
                title=_("Invalid Recipient"),
            )

    def validate_recipient_not_fully_paid(self):
        if not self.commission_recipient:
            return
        status = frappe.db.get_value(
            "Commission Recipient", self.commission_recipient, "payment_status"
        )
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
                _(
                    "Amount To Pay ({0}) exceeds the Remaining Due ({1}) for this recipient."
                ).format(
                    frappe.format_value(amount_to_pay, {"fieldtype": "Currency"}),
                    frappe.format_value(remaining, {"fieldtype": "Currency"}),
                ),
                title=_("Amount Exceeds Remaining Due"),
            )

    def validate_paying_account(self):
        if not self.paying_account:
            return

        account = frappe.db.get_value(
            "Account",
            self.paying_account,
            ["account_type", "is_group", "disabled"],
            as_dict=True,
        )
        if not account:
            frappe.throw(
                _("Paying Account <b>{0}</b> not found.").format(self.paying_account),
                title=_("Invalid Account"),
            )
        if account.is_group:
            frappe.throw(
                _("Paying Account <b>{0}</b> is a group account and cannot be used for transactions.").format(
                    self.paying_account
                ),
                title=_("Group Account Not Allowed"),
            )
        if account.disabled:
            frappe.throw(
                _("Paying Account <b>{0}</b> is disabled.").format(self.paying_account),
                title=_("Disabled Account"),
            )

    # ------------------------------------------------------------------ #
    #  Post-submit / cancel: Journal Entry + status sync                  #
    # ------------------------------------------------------------------ #

    def _update_parent_commission(self):
        """
        After submit or cancel, create/reverse the journal entry and
        tell the parent Sales Commission to recompute its payment status.
        """
        if self.docstatus == 1:
            self._create_journal_entry()
        elif self.docstatus == 2:
            self._cancel_journal_entry()

        commission_doc = frappe.get_doc("Sales Commission", self.commission)
        commission_doc.recompute_payment_status()

    def _create_journal_entry(self):
        """
        Debit: Expense Category's linked account (commission expense going out)
        Credit: Paying Account (bank/cash going out)
        """
        expense_account = frappe.db.get_value(
            "Expense Category", self.expense_category, "account"
        )
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

        remark = _(
            "Commission Payout: {0} to {1} | Ref Commission: {2} | Payout Ref: {3}"
        ).format(
            sales_person_name or self.commission_recipient,
            self.paying_account,
            self.commission,
            self.name,
        )

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.payout_date
        je.user_remark = remark
        je.reference_doctype = "Commission Payout"
        je.reference_name = self.name

        # Debit: commission expense account
        je.append(
            "accounts",
            {
                "account": expense_account,
                "debit_in_account_currency": flt(self.amount_to_pay),
                "credit_in_account_currency": 0,
                "reference_type": "Commission Payout",
                "reference_name": self.name,
                "user_remark": _("Commission expense for {0}").format(
                    sales_person_name or self.commission_recipient
                ),
            },
        )

        # Credit: paying account (bank/cash)
        je.append(
            "accounts",
            {
                "account": self.paying_account,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": flt(self.amount_to_pay),
                "reference_type": "Commission Payout",
                "reference_name": self.name,
                "user_remark": _("Commission payment from {0}").format(
                    self.paying_account
                ),
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
        je_name = frappe.db.get_value(
            "Commission Payout", self.name, "journal_entry"
        )
        if je_name:
            je_doc = frappe.get_doc("Journal Entry", je_name)
            if je_doc.docstatus == 1:
                je_doc.flags.ignore_permissions = True
                je_doc.cancel()