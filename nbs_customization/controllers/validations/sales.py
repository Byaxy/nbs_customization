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


def prepare_quotation_test_record(doc, method=None):
     """Test records built by the framework skip the app's mandatory RFQ number."""
     if not doc.custom_request_for_quotation_number:
          doc.custom_request_for_quotation_number = "TEST-RFQ-0001"
