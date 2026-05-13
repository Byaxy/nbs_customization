import frappe
from frappe import _


def before_insert(doc, method):
     """
     Rewrites batch_id into a composite unique key scoped to the item.

     Key structure:
          has_expiry_date = 1:  {item_code}-{YYYYMMDD}-{manufacturer_batch_no}
          has_expiry_date = 0:  {item_code}-{manufacturer_batch_no}

     The user-entered batch number is preserved in
     custom_batch_no for display, search, and reporting.
     """
     if not doc.item:
          return

     original = (doc.batch_id or "").strip()

     if not original:
          frappe.throw(_("Batch ID is required."))

     # Persist the original manufacturer-issued batch number before rewriting
     if not doc.custom_batch_no:
          doc.custom_batch_no = original

     has_expiry_date = frappe.db.get_value("Item", doc.item, "has_expiry_date")

     if has_expiry_date:
          if not doc.expiry_date:
               frappe.throw(
                    _("Expiry Date is mandatory for {0} before a batch can be created.").format(
                    frappe.bold(doc.item)
                    )
               )
          expiry_str = frappe.utils.getdate(doc.expiry_date).strftime("%Y%m%d")
          doc.batch_id = f"{original}-{expiry_str}-{doc.item}"
     else:
          # No expiry date involved — single dash, no gap in the key
          doc.batch_id = f"{original}-{doc.item}"
