# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, money_in_words


class Receipt(Document):
    _DOCTYPE_NAME = "Receipt"

    # ------------------------------------------------------------------ #
    # Lifecycle hooks                                                      #
    # ------------------------------------------------------------------ #

    def validate(self):
        self._fetch_payment_row_details()
        self._sync_payment_methods()
        self._compute_totals()
        self._compute_amount_in_words()
        self._compute_customer_outstanding()
        self._render_address_displays()

    def before_submit(self):
        self._validate_minimum_rows()
        self._validate_no_duplicates()

    def on_submit(self):
        self._update_payment_entries(action="submit")

    def on_cancel(self):
        self._update_payment_entries(action="cancel")

    # ------------------------------------------------------------------ #
    # Private — validate helpers                                           #
    # ------------------------------------------------------------------ #

    def _fetch_payment_row_details(self):
        """
        For each row in receipt_payments:
        - Populate invoice_date (read_only) from the linked Sales Invoice
        - Populate amount_due (read_only) from the Payment Entry Reference row
        - Auto-fill amount_received only when the row has no value yet
        - Always recompute balance_due
        - Auto-fill payment_method and receiving_account from the PE header if empty
        """
        for row in self.receipt_payments:

            # ---- invoice_date -----------------------------------------
            if row.sales_invoice:
                invoice_date = frappe.db.get_value(
                    "Sales Invoice", row.sales_invoice, "posting_date"
                )
                if invoice_date:
                    row.invoice_date = invoice_date

            # ---- amount_due / amount_received / balance_due from PE Reference --------
            # outstanding_amount on PE Reference is the post-payment remaining balance.
            # amount_due = pre-payment outstanding = outstanding + allocated.
            # balance_due = post-payment remaining = outstanding.
            if row.payment_entry and row.sales_invoice:
                pe_ref = frappe.db.get_value(
                    "Payment Entry Reference",
                    {
                        "parent": row.payment_entry,
                        "reference_name": row.sales_invoice,
                    },
                    ["outstanding_amount", "allocated_amount"],
                    as_dict=True,
                )
                if pe_ref:
                    row.amount_due = flt(pe_ref.outstanding_amount) + flt(
                        pe_ref.allocated_amount
                    )
                    if not row.amount_received:
                        row.amount_received = flt(pe_ref.allocated_amount)
                    row.balance_due = flt(pe_ref.outstanding_amount)

            # ---- payment_method from PE header (if empty) --------------
            if row.payment_entry and not row.payment_method:
                mode = frappe.db.get_value(
                    "Payment Entry", row.payment_entry, "mode_of_payment"
                )
                if mode:
                    row.payment_method = mode

            # ---- receiving_account from PE header (if empty) -----------
            if row.payment_entry and not row.receiving_account:
                paid_to = frappe.db.get_value(
                    "Payment Entry", row.payment_entry, "paid_to"
                )
                if paid_to:
                    row.receiving_account = paid_to

                # ---- reference_no / reference_date from PE -------------------------
            if row.payment_entry:
                ref_no, ref_date = frappe.db.get_value(
                    "Payment Entry",
                    row.payment_entry,
                    ["reference_no", "reference_date"],
                )
                row.reference_no = ref_no or ""
                row.reference_date = ref_date or None

    def _compute_totals(self):
        self.total_amount_due = sum(
            flt(row.amount_due) for row in self.receipt_payments
        )
        self.total_amount_received = sum(
            flt(row.amount_received) for row in self.receipt_payments
        )
        self.total_balance_due = sum(
            flt(row.balance_due)
            for row in self.receipt_payments
            if row.sales_invoice
        )

    def _compute_amount_in_words(self):
        currency = self.currency or frappe.db.get_value(
            "Company", self.company, "default_currency"
        )
        self.amount_in_words = money_in_words(
            self.total_amount_received, currency)

    def _compute_customer_outstanding(self):
        if not self.customer:
            self.customer_total_outstanding = 0
            return
        total = frappe.db.sql(
            """
            SELECT COALESCE(SUM(outstanding_amount), 0)
            FROM `tabSales Invoice`
            WHERE customer = %s
              AND company = %s
              AND docstatus = 1
              AND outstanding_amount > 0
        """,
            (self.customer, self.company),
        )
        self.customer_total_outstanding = flt(total[0][0])

    def _render_address_displays(self):
        from frappe.contacts.doctype.address.address import get_address_display

        if self.customer_address:
            self.customer_address_display = (
                get_address_display(self.customer_address) or ""
            )
        if self.billing_address:
            self.billing_address_display = (
                get_address_display(self.billing_address) or ""
            )

    def _sync_payment_methods(self):
        """
        Rebuild receipt_payment_methods from receipt_payments.

        Grouping key: (payment_method, reference_no or "")
        - Cash / modes with no reference: all rows collapse into one, amounts summed.
        - Cheque / Bank Transfer / Draft: one row per unique reference_no, so two
            different cheques or two different bank transfers stay as separate rows
            with their own cheque numbers and dates.

        bank_name is user-editable and is preserved across rebuilds so the user
        doesn't lose what they typed on re-save.
        """
        # Snapshot user-entered bank names before we clear the table.
        # Key matches the new row key so restoration is exact.
        existing_bank_names = {
            (row.payment_method, row.cheque_number or ""): row.bank_name
            for row in self.receipt_payment_methods
            if row.bank_name
        }

        # Aggregate by (payment_method, reference_no or "")
        aggregated = {}
        for row in self.receipt_payments:
            if not row.payment_method:
                continue

            key = (row.payment_method, row.reference_no or "")

            if key not in aggregated:
                aggregated[key] = {"amount": 0.0,
                                   "cheque_date": row.reference_date}

            aggregated[key]["amount"] += flt(row.amount_received)

            # Keep the first non-null date found for this key
            if not aggregated[key]["cheque_date"] and row.reference_date:
                aggregated[key]["cheque_date"] = row.reference_date

        # Rebuild
        self.receipt_payment_methods = []
        for (payment_method, reference_no), data in aggregated.items():
            self.append("receipt_payment_methods", {
                "payment_method": payment_method,
                "cheque_number": reference_no or None,
                "cheque_date": data["cheque_date"],
                "bank_name": existing_bank_names.get((payment_method, reference_no), ""),
                "amount": data["amount"],
            })

    def _validate_minimum_rows(self):
        if not self.receipt_payments:
            frappe.throw(
                _("At least one Payment Entry row is required before submitting.")
            )
        if self.total_amount_received <= 0:
            frappe.throw(
                _("Total Amount Received must be greater than zero before submitting.")
            )

    def _validate_no_duplicates(self):
        """
        Called in before_submit. Guards against two problems:
          1. The same PE + SI pair appearing more than once within this Receipt.
          2. The same PE + SI pair already being covered by another submitted Receipt.
        """
        seen = set()

        for row in self.receipt_payments:
            if not row.payment_entry:
                continue

            key = (row.payment_entry, row.sales_invoice or "")

            # Within-document duplicate
            if key in seen:
                frappe.throw(
                    _("Row {0}: Payment Entry {1} / Invoice {2} appears more than once in this Receipt.").format(
                        row.idx,
                        frappe.bold(row.payment_entry),
                        frappe.bold(row.sales_invoice or "—"),
                    )
                )
            seen.add(key)

            # Duplicate across other submitted Receipts
            filters = {
                "payment_entry": row.payment_entry,
                "docstatus": 1,
                "parent": ["!=", self.name],
            }
            if row.sales_invoice:
                filters["sales_invoice"] = row.sales_invoice

            existing = frappe.db.get_value(
                "Receipt Payment", filters, "parent")
            if existing:
                frappe.throw(
                    _("Row {0}: Payment Entry {1} for Invoice {2} is already covered by submitted Receipt {3}.").format(
                        row.idx,
                        frappe.bold(row.payment_entry),
                        frappe.bold(row.sales_invoice or "—"),
                        frappe.bold(existing),
                    )
                )

    # ------------------------------------------------------------------ #
    # Private — submit / cancel                                            #
    # ------------------------------------------------------------------ #

    def _update_payment_entries(self, action: str):
        """
        On submit: write this Receipt's name into custom_receipt on each linked PE.
        On cancel: clear it.

        Skips gracefully if the custom field has not yet been added to Payment Entry.
        To add the field: Customise Form → Payment Entry → add a Link field
        named custom_receipt pointing to Receipt.
        """
        if not frappe.get_meta("Payment Entry").has_field("custom_receipt"):
            return

        value = self.name if action == "submit" else None

        # Deduplicate — one PE can appear in multiple rows (multiple invoices)
        pe_names = {
            row.payment_entry for row in self.receipt_payments if row.payment_entry}
        for pe_name in pe_names:
            frappe.db.set_value("Payment Entry", pe_name,
                                "custom_receipt", value)


# ------------------------------------------------------------------ #
# Whitelisted server methods                                           #
# ------------------------------------------------------------------ #

@frappe.whitelist()
def get_payment_entry_details(payment_entry: str) -> dict:
    """
    Called from JS to pre-populate receipt_payments rows from a given
    Payment Entry. Used by:
      - The 'Add from Payment Entry' button on the Receipt form
      - The 'Create Receipt' shortcut on the Payment Entry form

    Returns:
      {
        rows: [ { payment_entry, sales_invoice, invoice_date, amount_due,
                  amount_received, balance_due, payment_method,
                  receiving_account, reference_no, reference_date }, ... ],
        mode_of_payment: str,
        paid_to: str,
      }
    """
    pe = frappe.get_doc("Payment Entry", payment_entry)

    if pe.docstatus != 1:
        frappe.throw(
            _("Payment Entry {0} must be submitted before it can be added to a Receipt.").format(
                frappe.bold(payment_entry)
            )
        )

    if pe.payment_type != "Receive":
        frappe.throw(
            _("Only 'Receive' type Payment Entries are valid for customer receipts. "
              "{0} is of type '{1}'.").format(
                frappe.bold(payment_entry), pe.payment_type
            )
        )

    rows = []
    for ref in pe.references:
        if ref.reference_doctype != "Sales Invoice":
            continue

        invoice_date = frappe.db.get_value(
            "Sales Invoice", ref.reference_name, "posting_date"
        )

        rows.append({
            "payment_entry": pe.name,
            "sales_invoice": ref.reference_name,
            "invoice_date": invoice_date,
            "amount_due": flt(ref.outstanding_amount) + flt(ref.allocated_amount),
            "amount_received": flt(ref.allocated_amount),
            "balance_due": flt(ref.outstanding_amount),
            "payment_method": pe.mode_of_payment,
            "receiving_account": pe.paid_to,
            "reference_no": pe.reference_no or "",
            "reference_date": pe.reference_date,
        })

    # PE with no SI references (advance payment or income-category payment)
    if not rows:
        rows.append({
            "payment_entry": pe.name,
            "sales_invoice": None,
            "invoice_date": None,
            "amount_due": 0,
            "amount_received": flt(pe.paid_amount),
            "balance_due": 0,
            "payment_method": pe.mode_of_payment,
            "receiving_account": pe.paid_to,
            "reference_no": pe.reference_no or "",
            "reference_date": pe.reference_date,
        })

    return {
        "rows": rows,
        "mode_of_payment": pe.mode_of_payment,
        "paid_to": pe.paid_to,
    }


@frappe.whitelist()
def get_customer_outstanding_invoices(customer: str, company: str) -> list:
    """
    Returns submitted Sales Invoices with an outstanding balance for the given
    customer. Useful for displaying the customer's full position when preparing
    a receipt, and as a helper for the print format's 'current balance' block.
    """
    return frappe.db.get_all(
        "Sales Invoice",
        filters={
            "customer": customer,
            "company": company,
            "docstatus": 1,
            "outstanding_amount": [">", 0],
        },
        fields=[
            "name",
            "posting_date",
            "grand_total",
            "outstanding_amount",
            "status",
        ],
        order_by="posting_date asc",
    )


def _set_customer_addresses(doc):
    from frappe.contacts.doctype.address.address import (
        get_address_display,
        get_default_address,
    )

    if not doc.customer:
        return

    customer_address = get_default_address("Customer", doc.customer)
    if customer_address:
        doc.customer_address = customer_address
        doc.customer_address_display = get_address_display(
            customer_address) or ""

    billing_address = get_default_address(
        "Customer", doc.customer, sort_key="is_shipping_address"
    )
    if not billing_address or billing_address == customer_address:
        doc.billing_address = doc.customer_address
        doc.billing_address_display = doc.customer_address_display
    else:
        doc.billing_address = billing_address
        doc.billing_address_display = get_address_display(
            billing_address) or ""


@frappe.whitelist()
def create_receipt_from_pe(source_name, target_doc=None):
    """
    Called from the Payment Entry "Create Receipt" button via
    frappe.model.open_mapped_doc.
    Returns a new draft Receipt pre-populated from the PE's data.
    """
    pe = frappe.get_doc("Payment Entry", source_name)

    if pe.docstatus != 1:
        frappe.throw(
            _("Payment Entry must be submitted before creating a Receipt.")
        )
    if pe.payment_type != "Receive":
        frappe.throw(
            _("Only Receive-type Payment Entries are supported.")
        )
    if pe.get("custom_receipt"):
        frappe.throw(
            _("Receipt {0} already exists for this Payment Entry.").format(
                frappe.bold(pe.custom_receipt)
            )
        )

    receipt = frappe.new_doc("Receipt")
    receipt.company = pe.company
    receipt.customer = pe.party
    receipt.receipt_date = getdate()
    receipt.currency = pe.paid_from_account_currency or frappe.db.get_value(
        "Company", pe.company, "default_currency"
    )

    _set_customer_addresses(receipt)

    details = get_payment_entry_details(source_name)
    for row_data in details["rows"]:
        receipt.append("receipt_payments", row_data)

    return receipt
