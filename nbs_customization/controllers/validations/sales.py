import frappe

def validate_unique_items(doc, method=None):
     seen_items = set()

     for row in doc.items:
          if row.item_code in seen_items:
               frappe.throw(
                    f"Item {row.item_code} appears multiple times "
                    f"(row #{row.idx}). Please combine quantities into one row."
               )

          seen_items.add(row.item_code)
