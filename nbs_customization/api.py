import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def get_nbs_theme():
    """
    Get NBS theme configuration
    Returns theme data for JavaScript theme manager
    """
    try:
        # Check if theme configuration exists
        if frappe.db.exists("NBS Theme Configuration"):
            theme = frappe.get_doc("NBS Theme Configuration")
            return theme.as_dict()
        else:
            # Return default theme configuration
            return {
                "primary_color": "#001b52",
                "danger_color": "#dc2626",
                "table_header_bg": "#001b52",
                "table_header_text": "#ffffff",
                "table_even_bg": "#eff6ff",
                "table_hover_bg": "#eff6ff",
                "navbar_bg": "#001b52",
                "navbar_text": "#ffffff",
                "login_title": "Biomedical Solutions",
                "login_title_color": "#001b52",
                "login_box_bg": "#ffffff",
                "login_box_width": "400px"
            }
    except Exception as e:
        frappe.log_error(f"Error getting NBS theme: {str(e)}")
        return {}

@frappe.whitelist(allow_guest=True)
def get_default_company():
    """Get the default company name for login page display"""
    try:
        # Use frappe.defaults.get_defaults() to get default company
        defaults = frappe.defaults.get_defaults()
        default_company = defaults.get('company')
        
        if default_company:
            # Get company name from Company doctype
            company_name = frappe.db.get_value("Company", default_company, "company_name")
            if company_name:
                return {"company_name": company_name}
        
        # Fallback: get any company
        companies = frappe.get_all("Company", fields=["company_name"], limit=1)
        if companies:
            return {"company_name": companies[0].company_name}
            
        # Final fallback
        return {"company_name": "NBS"}
        
    except Exception:
        return {"company_name": "NBS"}

@frappe.whitelist()
def save_nbs_theme(theme_data):
    """
    Save NBS theme configuration
    """
    try:
        if not frappe.has_permission("NBS Theme Configuration", "write"):
            return {"success": False, "message": "Permission denied"}
        
        # Check if theme configuration exists
        if frappe.db.exists("NBS Theme Configuration"):
            theme = frappe.get_doc("NBS Theme Configuration")
        else:
            theme = frappe.new_doc("NBS Theme Configuration")
        
        # Update theme data
        theme.update(theme_data)
        theme.save(ignore_permissions=True)
        
        return {"success": True, "message": "Theme saved successfully"}
    except Exception as e:
        frappe.log_error(f"Error saving NBS theme: {str(e)}")
        return {"success": False, "message": str(e)}

@frappe.whitelist()
def reset_nbs_theme():
    """
    Reset NBS theme to defaults
    """
    try:
        if not frappe.has_permission("NBS Theme Configuration", "write"):
            return {"success": False, "message": "Permission denied"}
        
        # Delete existing theme configuration
        if frappe.db.exists("NBS Theme Configuration"):
            frappe.delete_doc("NBS Theme Configuration")
        
        return {"success": True, "message": "Theme reset successfully"}
    except Exception as e:
        frappe.log_error(f"Error resetting NBS theme: {str(e)}")
        return {"success": False, "message": str(e)}
