import frappe


def before_cancel(doc, method=None):
    if not getattr(doc, "custom_is_loan", 0):
        return

    if getattr(frappe.flags, "allow_cancel_loan_stock_entry", False):
        return

    frappe.throw(
        "This Stock Entry was created from a Loan Waybill and cannot be cancelled directly. "
        "Cancel the Loan Waybill instead."
    )
