# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


def calculate_commission_amounts(
    amount_received: float,
    additions: float,
    deductions: float,
    commission_rate: float,       # as decimal, e.g. 0.10
    withholding_tax_rate: float,  # as decimal, e.g. 0.03
) -> dict:

    wht_on_invoice = flt(amount_received) * flt(withholding_tax_rate)
    actual_received = flt(amount_received) - wht_on_invoice
    wht_amount = actual_received * flt(withholding_tax_rate)
    base = max(0.0, actual_received - wht_amount - flt(additions))
    gross = base * flt(commission_rate)
    net = max(0.0, gross - flt(deductions))

    return {
        "base_for_commission": flt(base, 2),
        "gross_commission": flt(gross, 2),
        "withholding_tax_amount": flt(wht_amount, 2),
        "commission_payable": flt(net, 2),
    }


class SalesCommission(Document):
    # ------------------------------------------------------------------ #
    #  Lifecycle hooks                                                     #
    # ------------------------------------------------------------------ #

    def validate(self):
        self.validate_commission_date()
        self.validate_commission_sales()
        self.validate_recipients()
        self.calculate_row_amounts()
        self.calculate_totals()
        self.sync_recipient_remaining_due()
        self.validate_recipients_allocation()

    def before_submit(self):
        """Submission = Approval. Run final checks before locking the document."""
        self.flag_invoices_as_commissioned(True)

    def on_cancel(self):
        self.validate_no_payouts_on_cancel()
        self.flag_invoices_as_commissioned(False)
        self._set_recipients_cancelled()

    # ------------------------------------------------------------------ #
    #  Validation helpers                                                  #
    # ------------------------------------------------------------------ #

    def validate_commission_date(self):
        if not self.commission_date:
            frappe.throw(_("Commission Date is required."), title=_("Missing Field"))

    def validate_commission_sales(self):
        if not self.commission_sales:
            frappe.throw(
                _("At least one Commission Sale Entry is required."),
                title=_("Validation Error"),
            )

        seen_invoices = set()
        for i, row in enumerate(self.commission_sales):
            row_label = f"Row {i + 1}"
            if not row.sale:
                frappe.throw(
                    _("{0} in Commission Sales: Sales Invoice is required.").format(row_label),
                    title=_("Validation Error"),
                )
            if row.sale in seen_invoices:
                frappe.throw(
                    _("{0}: Sales Invoice <b>{1}</b> is already added. Each invoice can only appear once.").format(
                        row_label, row.sale
                    ),
                    title=_("Duplicate Invoice"),
                )
            seen_invoices.add(row.sale)

            if flt(row.commission_rate) <= 0:
                frappe.throw(
                    _("{0}: Commission Rate must be greater than 0 for invoice <b>{1}</b>.").format(
                        row_label, row.sale
                    ),
                    title=_("Validation Error"),
                )
            if flt(row.commission_rate) > 100:
                frappe.throw(
                    _("{0}: Commission Rate cannot exceed 100% for invoice <b>{1}</b>.").format(
                        row_label, row.sale
                    ),
                    title=_("Validation Error"),
                )

            # Block invoices already commissioned on another active commission
            if self.is_new() or self._is_new_sale_row(row):
                self._check_invoice_not_already_commissioned(row.sale)

    def validate_recipients(self):
        if not self.commission_recipients:
            frappe.throw(
                _("At least one Commission Recipient is required."),
                title=_("Validation Error"),
            )

        seen_agents = set()
        for i, row in enumerate(self.commission_recipients):
            row_label = f"Recipient Row {i + 1}"
            if not row.sales_person:
                frappe.throw(
                    _("{0}: Sales Person is required.").format(row_label),
                    title=_("Validation Error"),
                )
            if row.sales_person in seen_agents:
                frappe.throw(
                    _("{0}: Sales Person <b>{1}</b> is listed more than once.").format(
                        row_label, row.sales_person
                    ),
                    title=_("Duplicate Recipient"),
                )
            seen_agents.add(row.sales_person)

            if flt(row.allocated_amount) <= 0:
                frappe.throw(
                    _("{0}: Allocated Amount must be greater than 0 for <b>{1}</b>.").format(
                        row_label, row.sales_person
                    ),
                    title=_("Validation Error"),
                )

    def validate_recipients_allocation(self):
        """
        Called before_submit. Warns if total recipient allocation differs from
        total_commission_payable. Throws if allocation exceeds it.
        """
        total_allocated = sum(flt(r.allocated_amount) for r in self.commission_recipients)
        total_payable = flt(self.total_commission_payable)

        if flt(total_allocated, 2) > flt(total_payable, 2):
            frappe.throw(
                _(
                    "Total Allocated Amount ({0}) exceeds Total Commission Payable ({1}). "
                    "Please adjust recipient allocations."
                ).format(
                    frappe.format_value(total_allocated, {"fieldtype": "Currency"}),
                    frappe.format_value(total_payable, {"fieldtype": "Currency"}),
                ),
                title=_("Allocation Mismatch"),
            )

        if flt(total_allocated, 2) < flt(total_payable, 2):
            # Warn but allow — partial distribution is a valid business choice
            frappe.msgprint(
                _(
                    "Note: Total Allocated Amount ({0}) is less than Total Commission Payable ({1}). "
                    "The unallocated balance of {2} will not be tracked against any recipient."
                ).format(
                    frappe.format_value(total_allocated, {"fieldtype": "Currency"}),
                    frappe.format_value(total_payable, {"fieldtype": "Currency"}),
                    frappe.format_value(total_payable - total_allocated, {"fieldtype": "Currency"}),
                ),
                title=_("Partial Allocation"),
                indicator="orange",
            )

    def validate_no_payouts_on_cancel(self):
        """Prevent cancellation if any payout has been submitted against this commission."""
        paid_recipients = []
        for row in self.commission_recipients:
            paid = flt(row.paid_amount)
            if paid > 0:
                paid_recipients.append(f"<b>{row.sales_person}</b> (paid: {frappe.format_value(paid, {'fieldtype': 'Currency'})})")

        if paid_recipients:
            frappe.throw(
                _(
                    "Cannot cancel this Commission because the following recipients have already received payouts:<br>"
                    "{0}<br><br>Please cancel individual Commission Payouts first."
                ).format("<br>".join(paid_recipients)),
                title=_("Cancel Not Allowed"),
            )

    # ------------------------------------------------------------------ #
    #  Calculation helpers                                                 #
    # ------------------------------------------------------------------ #

    def calculate_row_amounts(self):
        """Recalculate all computed fields on every Commission Sale Entry row."""
        for row in self.commission_sales:
            if not row.sale:
                continue

            # total_amount is fetched from Sales Invoice via fetch_from; fall back to 0
            amount_received = flt(row.total_amount)
            additions = flt(row.additions)
            deductions = flt(row.deductions)
            commission_rate = flt(row.commission_rate) / 100.0
            wht_rate = flt(row.withholding_tax_rate) / 100.0

            result = calculate_commission_amounts(
                amount_received, additions, deductions, commission_rate, wht_rate
            )

            row.base_for_commission = result["base_for_commission"]
            row.gross_commission = result["gross_commission"]
            row.withholding_tax_amount = result["withholding_tax_amount"]
            row.commission_payable = result["commission_payable"]

    def calculate_totals(self):
        """Aggregate row-level amounts into the parent totals fields."""
        self.total_amount = flt(sum(flt(r.total_amount) for r in self.commission_sales), 2)
        self.total_additions = flt(sum(flt(r.additions) for r in self.commission_sales), 2)
        self.total_deductions = flt(sum(flt(r.deductions) for r in self.commission_sales), 2)
        self.total_base_for_commission = flt(
            sum(flt(r.base_for_commission) for r in self.commission_sales), 2
        )
        self.total_gross_commission = flt(
            sum(flt(r.gross_commission) for r in self.commission_sales), 2
        )
        self.total_withholding_tax_amount = flt(
            sum(flt(r.withholding_tax_amount) for r in self.commission_sales), 2
        )
        self.total_commission_payable = flt(
            sum(flt(r.commission_payable) for r in self.commission_sales), 2
        )

    def sync_recipient_remaining_due(self):
        """Keep remaining_due in sync with allocated_amount and paid_amount."""
        for row in self.commission_recipients:
            row.remaining_due = flt(
                flt(row.allocated_amount) - flt(row.paid_amount), 2
            )

    # ------------------------------------------------------------------ #
    #  Invoice commission flag helpers                                     #
    # ------------------------------------------------------------------ #

    def flag_invoices_as_commissioned(self, flag: bool):
        """Set custom_is_commission_applied on all linked Sales Invoices."""
        for row in self.commission_sales:
            if row.sale:
                frappe.db.set_value(
                    "Sales Invoice",
                    row.sale,
                    "custom_is_commission_applied",
                    1 if flag else 0,
                )

    def _check_invoice_not_already_commissioned(self, invoice_name: str):
        """
        Ensure the invoice isn't already tied to another active (non-cancelled)
        Sales Commission (excluding the current document).
        """
        filters = {
            "sale": invoice_name,
            "docstatus": ["!=", 2],  # not cancelled
        }
        existing = frappe.db.get_value(
            "Commission Sale Entry",
            filters,
            ["parent"],
            as_dict=True,
        )
        if existing and existing.parent != self.name:
            frappe.throw(
                _(
                    "Sales Invoice <b>{0}</b> is already included in Commission "
                    "<b>{1}</b>. An invoice can only be commissioned once."
                ).format(invoice_name, existing.parent),
                title=_("Invoice Already Commissioned"),
            )

    def _is_new_sale_row(self, row) -> bool:
        """True if this row doesn't yet exist in the saved document."""
        if self.is_new():
            return True
        return not frappe.db.exists(
            "Commission Sale Entry", {"name": row.name, "parent": self.name}
        )

    def _set_recipients_cancelled(self):
        for row in self.commission_recipients:
            if row.payment_status not in ("Paid", "Partial"):
                row.payment_status = "Cancelled"
        self.db_update()

    # ------------------------------------------------------------------ #
    #  Public method: called by Commission Payout on_submit / on_cancel   #
    # ------------------------------------------------------------------ #

    def recompute_payment_status(self):
        """
        Called externally (from Commission Payout) after a payout is submitted
        or cancelled. Refreshes paid_amount, remaining_due, and payment_status
        for every recipient, then sets the parent commission payment_status.
        """
        commission_fully_paid = True
        any_partial = False
        any_paid = False

        for row in self.commission_recipients:
            total_paid = flt(
                frappe.db.sql(
                    """
                    SELECT COALESCE(SUM(cp.amount_to_pay), 0)
                    FROM `tabCommission Payout` cp
                    WHERE cp.commission_recipient = %s
                      AND cp.docstatus = 1
                    """,
                    (row.name,),
                )[0][0]
            )

            allocated = flt(row.allocated_amount)
            row.paid_amount = flt(total_paid, 2)
            row.remaining_due = flt(max(0.0, allocated - total_paid), 2)

            if flt(total_paid, 2) >= flt(allocated, 2) - 0.01:
                row.payment_status = "Paid"
                any_paid = True
            elif total_paid > 0:
                row.payment_status = "Partial"
                any_partial = True
                commission_fully_paid = False
            else:
                row.payment_status = "Pending"
                commission_fully_paid = False

            if row.payment_status != "Paid":
                any_paid_flag = row.paid_amount > 0
                if any_paid_flag:
                    any_paid = True

        if commission_fully_paid:
            new_status = "Paid"
        elif any_partial or any_paid:
            new_status = "Partial"
        else:
            new_status = "Pending"

        self.payment_status = new_status
        self.db_update()


# ------------------------------------------------------------------ #
#  Whitelisted server methods (called from JS)                        #
# ------------------------------------------------------------------ #

@frappe.whitelist()
def get_wht_rate_for_category(tax_withholding_category: str) -> float:
    """
    Fetch the current withholding tax rate from Tax Withholding Category.
    Returns the rate from the most recent applicable fiscal year row.
    """
    if not tax_withholding_category:
        return 0.0

    posting_date = nowdate()

    # Try rate valid for today's date first
    rate = frappe.db.get_value(
        "Tax Withholding Rate",
        {
            "parent": tax_withholding_category,
            "from_date": ("<=", posting_date),
            "to_date": (">=", posting_date),
        },
        "tax_withholding_rate",
        order_by="from_date desc",
    )

    # Fall back to latest dated rate defined on this category
    if rate is None:
        rate = frappe.db.get_value(
            "Tax Withholding Rate",
            {"parent": tax_withholding_category},
            "tax_withholding_rate",
            order_by="to_date desc, from_date desc",
        )

    return abs(flt(rate)) if rate is not None else 0.0


@frappe.whitelist()
def get_invoices_for_customer(customer: str) -> list:
    """
    Return submitted, unpaid/partially-paid Sales Invoices for a customer
    that have not yet been assigned to an active (non-cancelled) commission.
    """
    if not customer:
        return []

    # Invoices already locked in an active commission
    commissioned_invoices = frappe.db.sql_list(
        """
        SELECT DISTINCT cse.sale
        FROM `tabCommission Sale Entry` cse
        INNER JOIN `tabSales Commission` sc ON sc.name = cse.parent
        WHERE sc.docstatus != 2
        """
    )

    filters = {
        "customer": customer,
        "docstatus": 1,
        "status": ["in", ["Unpaid", "Partly Paid", "Overdue"]],
    }

    invoices = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=["name", "posting_date", "grand_total", "outstanding_amount", "status"],
        order_by="posting_date desc",
    )

    # Exclude already commissioned invoices
    return [inv for inv in invoices if inv["name"] not in commissioned_invoices]


@frappe.whitelist()
def get_recipients_for_commission(commission: str) -> list:
    """
    Return Commission Recipient child rows for a given Sales Commission
    that are NOT yet fully paid (Pending or Partial), so the payout form
    can filter its recipient link field.
    """
    if not commission:
        return []

    doc = frappe.get_doc("Sales Commission", commission)
    result = []
    for row in doc.commission_recipients:
        if row.payment_status not in ("Paid", "Cancelled"):
            result.append(
                {
                    "name": row.name,
                    "sales_person": row.sales_person,
                    "allocated_amount": flt(row.allocated_amount),
                    "paid_amount": flt(row.paid_amount),
                    "remaining_due": flt(row.remaining_due),
                    "payment_status": row.payment_status,
                }
            )
    return result