# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def before_cancel(doc, method=None):
    """
    Prevent direct cancellation of a Stock Entry that was created by a Loan Waybill.
    The Loan Waybill's on_cancel sets the allow-flag before calling se.cancel(),
    so that path bypasses this guard cleanly.
    """
    if not getattr(doc, "custom_is_loan", 0):
        return

    if getattr(frappe.flags, "allow_cancel_loan_stock_entry", False):
        return

    frappe.throw(
        _(
            "This Stock Entry was created by a Loan Waybill and cannot be cancelled directly. "
            "Cancel the Loan Waybill instead."
        )
    )