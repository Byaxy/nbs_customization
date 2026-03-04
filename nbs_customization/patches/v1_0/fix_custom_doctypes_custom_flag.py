import frappe

def execute():
    """
    Fix custom flag for all custom DocTypes in production database.
    This patch converts custom DocTypes to app-owned DocTypes.
    """
    doctypes = [
        "Loan Waybill",
        "Loan Waybill Item", 
        "Loan Conversion History",
        "Loan Waybill Batch Balance",
        "Customer Delivery Note",
        "Customer Delivery Note Item",
        "Promissory Note",
        "Promissory Note Item",
        "Item Type"
    ]
    
    updated_count = 0
    
    for dt in doctypes:
        if frappe.db.exists("DocType", dt):
            current_custom = frappe.db.get_value("DocType", dt, "custom")
            if current_custom == 1:
                frappe.db.set_value("DocType", dt, "custom", 0, update_modified=False)
                updated_count += 1
                print(f"Updated {dt}: custom flag set to 0")
            else:
                print(f"{dt} already has custom flag = {current_custom}")
        else:
            print(f"DocType {dt} not found in database")
    
    frappe.db.commit()
    print(f"Fixed custom flag for {updated_count} DocTypes")
