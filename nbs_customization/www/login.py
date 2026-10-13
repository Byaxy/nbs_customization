"""NBS two-column login — extends the stock Frappe login context.

Only adds branding variables; all auth flows (password, LDAP,
email-link, social, signup, forgot) are inherited untouched from
frappe.www.login so the stock login.js keeps working.
"""

import frappe


def get_context(context):
	from frappe.www.login import get_context as original_get_context

	original_get_context(context)
	context.full_width = True

	theme = {}
	company = "NBS"
	try:
		from nbs_customization.api import get_default_company, get_desk_theme

		theme = get_desk_theme() or {}
		company = (get_default_company() or {}).get("company_name") or company
	except Exception:
		frappe.log_error(frappe.get_traceback(), "nbs_login_context failed")

	context.nbs_theme = frappe._dict(theme)
	context.nbs_company = company
	context.nbs_logo = frappe.db.get_single_value("Navbar Settings", "app_logo") or ""
	return context
