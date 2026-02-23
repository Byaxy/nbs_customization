import frappe

def validate_unique_item_batch(doc, method=None):
     seen = set()

     for row in doc.items:
          batch_no = getattr(row, "batch_no", "") or ""
          serial_no = getattr(row, "serial_no", "") or ""

          key = (row.item_code, batch_no, serial_no)

          if key in seen:
               frappe.throw(
                    f"Duplicate entry for Item {row.item_code} "
                    f"with same Batch/Serial in row #{row.idx}."
               )

          seen.add(key)
