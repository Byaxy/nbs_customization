# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

# ---------------------------------------------------------------------------
# Core commission calculation
# ---------------------------------------------------------------------------

def calculate_commission_amounts(
    grand_total: float,       
    wht_amount: float,       
    additions: float,         
    deductions: float,        
    commission_rate: float,   
) -> dict:
    """
    Calculate commission amounts
    """
    gt  = flt(grand_total)
    wht = flt(wht_amount)
    add = flt(additions)
    ded = flt(deductions)
    cr  = flt(commission_rate)

    base    = max(0.0, gt - wht - add)
    gross   = base * cr
    payable = max(0.0, gross - ded)

    return {
        "wht_amount":             flt(wht, 2),
        "base_for_commission":    flt(base, 2),
        "gross_commission":       flt(gross, 2),
        "commission_payable":     flt(payable, 2),
        "withholding_tax_amount": flt(wht, 2),
    }


def _get_invoice_wht_details(invoice: str) -> dict:
    wht_rate = 0.0
    wht_amount = 0.0
    consider_for_wht = False
    tax_withholding_category = ""

    if not invoice:
        return {
            "consider_for_wht": consider_for_wht,
            "wht_category": tax_withholding_category,
            "wht_rate": wht_rate,
            "wht_amount": wht_amount,
        }

    apply_tds = frappe.db.get_value("Sales Invoice", invoice, "apply_tds")
    consider_for_wht = bool(apply_tds)

    if consider_for_wht:
        tax_row = frappe.db.get_value(
            "Tax Withholding Entry",
            {
                "parent": invoice,
                "parenttype": "Sales Invoice",
                "tax_rate": ["<", 0],
            },
            ["tax_rate", "withholding_amount", "tax_withholding_category"],
            as_dict=True,
            order_by="idx asc",
        )
        if tax_row:
            wht_rate = abs(flt(tax_row.tax_rate))
            wht_amount = abs(flt(tax_row.withholding_amount))
            tax_withholding_category = tax_row.tax_withholding_category

    return {
        "consider_for_wht": consider_for_wht,
        "wht_category": tax_withholding_category,
        "wht_rate": wht_rate,
        "wht_amount": wht_amount,
    }


# ---------------------------------------------------------------------------
# DocType controller
# ---------------------------------------------------------------------------

class SalesCommission(Document):
    # ------------------------------------------------------------------ #
    #  Lifecycle hooks                                                     #
    # ------------------------------------------------------------------ #

    def validate(self):
        self._set_company_defaults()
        self.validate_commission_date()
        self.validate_commission_sales()
        self.validate_recipients()
        self.calculate_row_amounts()
        self.calculate_totals()
        self.sync_recipient_remaining_due()
        self.validate_recipients_allocation()

    def before_submit(self):
        self.flag_invoices_as_commissioned(True)

    def on_cancel(self):
        self.validate_no_payouts_on_cancel()
        self.flag_invoices_as_commissioned(False)
        self._set_recipients_cancelled()

    # ------------------------------------------------------------------ #
    #  Validation helpers                                                  #
    # ------------------------------------------------------------------ #

    def _set_company_defaults(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company")
        if not self.cost_center:
            self.cost_center = frappe.db.get_value(
                "Company", self.company, "cost_center"
            )

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
                    _("{0}: Sales Invoice is required.").format(row_label),
                    title=_("Validation Error"),
                )
            if row.sale in seen_invoices:
                frappe.throw(
                    _("{0}: Sales Invoice <b>{1}</b> is already added.").format(row_label, row.sale),
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
        total_allocated = sum(flt(r.allocated_amount) for r in self.commission_recipients)
        total_payable   = flt(self.total_commission_payable)

        if flt(total_allocated, 2) > flt(total_payable, 2):
            frappe.throw(
                _(
                    "Total Allocated Amount ({0}) exceeds Total Commission Payable ({1}). "
                    "Please adjust recipient allocations."
                ).format(
                    frappe.format_value(total_allocated, {"fieldtype": "Currency"}),
                    frappe.format_value(total_payable,   {"fieldtype": "Currency"}),
                ),
                title=_("Allocation Mismatch"),
            )

        if flt(total_allocated, 2) < flt(total_payable, 2):
            frappe.throw(
                _(
                    "Total Allocated ({0}) is less than Total Commission Payable ({1}). "
                    "Unallocated balance of {2} needs to be allocated to a recipient."
                ).format(
                    frappe.format_value(total_allocated,                      {"fieldtype": "Currency"}),
                    frappe.format_value(total_payable,                        {"fieldtype": "Currency"}),
                    frappe.format_value(total_payable - total_allocated,      {"fieldtype": "Currency"}),
                ),
                title=_("Partial Allocation"),
            )

    def validate_no_payouts_on_cancel(self):
        paid_recipients = [
            f"<b>{r.sales_person}</b> (paid: {frappe.format_value(flt(r.paid_amount), {'fieldtype': 'Currency'})})"
            for r in self.commission_recipients
            if flt(r.paid_amount) > 0
        ]
        if paid_recipients:
            frappe.throw(
                _(
                    "Cannot cancel this Commission because the following recipients have already "
                    "received payouts:<br>{0}<br><br>Please cancel individual Commission Payouts first."
                ).format("<br>".join(paid_recipients)),
                title=_("Cancel Not Allowed"),
            )

    # ------------------------------------------------------------------ #
    #  Calculation helpers                                                 #
    # ------------------------------------------------------------------ #

    def calculate_row_amounts(self):
        """
        Recalculate every Commission Sale Entry row.

        WHT amount is fetched fresh from the invoice's Tax Withholding Entry
        child table on every validate pass. We do NOT rely on row.withholding_tax_amount
        because that field is read_only in the DocType — Frappe strips read-only
        field values from the form payload before validate runs, so the row value
        would always be 0 on first save, causing a mismatch with the frontend.
        """
        for row in self.commission_sales:
            if not row.sale:
                continue

            # Always use Sales Invoice grand_total as the authoritative total_amount.
            # This keeps calculations consistent for invoices with WHT (grand_total is net payable).
            row.total_amount = flt(
                frappe.db.get_value("Sales Invoice", row.sale, "grand_total")
            )

            wht = _get_invoice_wht_details(row.sale)
            wht_amount = flt(wht.get("wht_amount"))
            if wht.get("consider_for_wht") and wht.get("wht_category"):
                row.withholding_tax_amount = flt(wht.get("wht_amount"))
                row.withholding_tax_rate = flt(wht.get("wht_rate"))
            else:
                row.withholding_tax_amount = 0
                row.withholding_tax_rate = 0

            result = calculate_commission_amounts(
                grand_total=flt(row.total_amount),
                wht_amount=wht_amount,
                additions=flt(row.additions),
                deductions=flt(row.deductions),
                commission_rate=flt(row.commission_rate) / 100.0,
            )

            row.base_for_commission = result["base_for_commission"]
            row.gross_commission    = result["gross_commission"]
            row.commission_payable  = result["commission_payable"]



    def calculate_totals(self):
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
        for row in self.commission_recipients:
            row.remaining_due = flt(flt(row.allocated_amount) - flt(row.paid_amount), 2)

    # ------------------------------------------------------------------ #
    #  Invoice flag helpers                                                #
    # ------------------------------------------------------------------ #

    def flag_invoices_as_commissioned(self, flag: bool):
        for row in self.commission_sales:
            if row.sale:
                frappe.db.set_value(
                    "Sales Invoice", row.sale,
                    "custom_is_commission_applied", 1 if flag else 0,
                )

    def _check_invoice_not_already_commissioned(self, invoice_name: str):
        existing = frappe.db.get_value(
            "Commission Sale Entry",
            {"sale": invoice_name, "docstatus": ["!=", 2]},
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
    #  Called by Commission Payout on_submit / on_cancel                  #
    # ------------------------------------------------------------------ #

    def recompute_payment_status(self):
        commission_fully_paid = True
        any_partial = False
        any_paid    = False

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
            row.paid_amount   = flt(total_paid, 2)
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

            if row.payment_status != "Paid" and row.paid_amount > 0:
                any_paid = True

        if commission_fully_paid:
            new_status = "Paid"
        elif any_partial or any_paid:
            new_status = "Partial"
        else:
            new_status = "Pending"

        self.payment_status = new_status

        for row in self.commission_recipients:
            row.db_update()

        self.db_update()


# ---------------------------------------------------------------------------
# Whitelisted server methods
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_invoice_details_for_commission(invoice: str) -> dict:
    """
    Single round-trip called from the JS `sale` event handler.

    Returns everything needed to populate a Commission Sale Entry row:
      - grand_total        : the full receivable (ERPNext has already netted out
                             the first WHT deduction from the customer)
      - consider_for_wht   : whether "Apply Tax Withholding Amount" is checked
      - wht_category       : Tax Withholding Category name (for display)
      - wht_rate           : WHT rate as a percentage (e.g. 3.0)
                             sourced from the invoice's Tax Withholding Entry row
                             so it matches what ERPNext actually used
      - wht_amount_on_inv  : the WHT amount ERPNext removed from the invoice total
                             (informational — shown to user but NOT used in formula)
    """
    if not invoice:
        return {}

    inv = frappe.db.get_value(
        "Sales Invoice",
        invoice,
        ["grand_total", "customer", "customer_name", "apply_tds"],
        as_dict=True,
    )
    if not inv:
        return {}

    wht = _get_invoice_wht_details(invoice)

    return {
        "grand_total":        flt(inv.grand_total),
        "customer":           inv.customer,
        "customer_name":      inv.customer_name,
        "consider_for_wht":   bool(wht.get("consider_for_wht")),
        "wht_category":       wht.get("wht_category"),
        "wht_rate":           flt(wht.get("wht_rate")),
        "wht_amount_on_inv":  flt(wht.get("wht_amount")),
    }


@frappe.whitelist()
def get_invoices_for_customer(doctype, txt, searchfield, start, page_len, filters):
    """
    Query submitted, PAID Sales Invoices for a customer not yet
    assigned to an active Sales Commission. Compatible with Link field query.
    """
    customer = filters.get("customer")
    if not customer:
        return []

    # Get already commissioned invoices to exclude them
    commissioned = frappe.db.sql_list(
        """
        SELECT DISTINCT cse.sale
        FROM `tabCommission Sale Entry` cse
        INNER JOIN `tabSales Commission` sc ON sc.name = cse.parent
        WHERE sc.docstatus != 2
        """
    )

    # Base query
    query = """
        SELECT name, customer_name, posting_date, grand_total
        FROM `tabSales Invoice`
        WHERE customer = %(customer)s
          AND docstatus = 1
          AND status = 'Paid'
    """
    params = {"customer": customer}

    if commissioned:
        query += " AND name NOT IN %(commissioned)s"
        params["commissioned"] = commissioned

    if txt:
        query += " AND name LIKE %(txt)s"
        params["txt"] = f"%{txt}%"

    query += f" ORDER BY posting_date DESC LIMIT {int(page_len)} OFFSET {int(start)}"

    results = frappe.db.sql(query, params)
    
    # Format grand_total as currency for the display in the Link selection
    formatted_results = []
    for row in results:
        res = list(row)
        if len(res) > 3:
            res[3] = frappe.format_value(res[3], {"fieldtype": "Currency"})
        formatted_results.append(res)
        
    return formatted_results


@frappe.whitelist()
def get_recipients_for_commission(commission: str) -> list:
    """Return unpaid/partial recipients for the Commission Payout link filter."""
    if not commission:
        return []

    doc = frappe.get_doc("Sales Commission", commission)
    return [
        {
            "name":             row.name,
            "sales_person":     row.sales_person,
            "allocated_amount": flt(row.allocated_amount),
            "paid_amount":      flt(row.paid_amount),
            "remaining_due":    flt(row.remaining_due),
            "payment_status":   row.payment_status,
        }
        for row in doc.commission_recipients
        if row.payment_status not in ("Paid", "Cancelled")
    ]


@frappe.whitelist()
def calculate_commission_row(
    grand_total: float,
    wht_amount: float,
    additions: float,
    deductions: float,
    commission_rate: float,   # as percentage e.g. 10
) -> dict:
    """Called directly from JS _recalculate_row — single source of truth for the formula."""
    result = calculate_commission_amounts(
        grand_total=flt(grand_total),
        wht_amount=flt(wht_amount),
        additions=flt(additions),
        deductions=flt(deductions),
        commission_rate=flt(commission_rate) / 100.0,
    )
    return result