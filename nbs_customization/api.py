# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _

CACHE_KEY = "nbs_desk_theme"

NBS_DEFAULTS = {
	"primary_color":                       "#001b52",
	"primary_hover":                       "#001540",
	"danger_color":                        "#dc2626",
	"danger_hover":                        "#b91c1c",
	"accent_color":				    "#00fdff",
	"sidebar_background":                  "#e8e9e9",
	"sidebar_text_color":                  "#001b52",
	"active_item_background":              "#001b52",
	"active_item_text":                    "#00fdff",
	"navbar_background":                   "#001b52",
	"navbar_text_color":                   "#ffffff",
	"navbar_icon_color":                   "#ffffff",
	"page_head_bg":                        "#e8e9e9",
	"page_head_text":                      "#001b52",
	"table_header_bg":                     "#001b52",
	"table_header_text":                   "#ffffff",
	"even_row_background":                 "#eff6ff",
	"table_row_hover_background":          "#dbeafe",
	"selectdropdown_row_hover_background": "#e0f2fe",
	"child_table_header_background":       "#001b52",
	"child_table_header_text":             "#ffffff",
	"primary_button_bg":                   "#001b52",
	"primary_button_hover":                "#001540",
	"primary_button_text":                 "#ffffff",
	"danger_button_bg":                    "#dc2626",
	"danger_button_hover":                 "#b91c1c",
	"login_title_color":                   "#001b52",
	"login_button_color":                  "#001b52",
	"login_bg_color":                      "#f1f5f9",
	"login_box_bg":                        "#ffffff",
}


# ---------------------------------------------------------------------------
# Desk Theme API
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_desk_theme():
	cached = frappe.cache().get_value(CACHE_KEY)
	if cached:
		return cached

	saved = frappe.db.get_singles_dict("Desk Theme") or {}
	config = _build_config(saved)
	frappe.cache().set_value(CACHE_KEY, config, expires_in_sec=86400)
	return config

def _sanitize_color(value):
    """Ensure color values have a # prefix — singles sometimes strip it."""
    if not value:
        return value
    value = value.strip()
    if value and not value.startswith("#"):
        return f"#{value}"
    return value


def _build_config(saved):
    def v(fieldname):
        raw = saved.get(fieldname) or NBS_DEFAULTS.get(fieldname, "")
        # Only sanitize actual color fields, not text fields like login_title
        if fieldname != "login_title":
            return _sanitize_color(raw)
        return raw

    return {
        "primaryColor":        v("primary_color"),
        "primaryHover":        v("primary_hover"),
        "dangerColor":         v("danger_color"),
        "dangerHover":         v("danger_hover"),
	   "accentColor":		 v("accent_color"),
        "sidebarBg":           v("sidebar_background"),
        "sidebarText":         v("sidebar_text_color"),
        "sidebarActiveItemBg": v("active_item_background"),
        "sidebarActiveText":   v("active_item_text"),
        "navbarBg":            v("navbar_background"),
        "navbarText":          v("navbar_text_color"),
        "navbarIcon":          v("navbar_icon_color"),
        "pageHeadBg":          v("page_head_bg"),
        "pageHeadText":        v("page_head_text"),
        "tableHeaderBg":       v("table_header_bg"),
        "tableHeaderText":     v("table_header_text"),
        "tableEvenBg":         v("even_row_background"),
        "tableRowHoverBg":     v("table_row_hover_background"),
        "selectRowHoverBg":    v("selectdropdown_row_hover_background"),
        "childHeaderBg":       v("child_table_header_background"),
        "childHeaderText":     v("child_table_header_text"),
        "btnPrimaryBg":        v("primary_button_bg"),
        "btnPrimaryHover":     v("primary_button_hover"),
        "btnPrimaryText":      v("primary_button_text"),
        "btnDangerBg":         v("danger_button_bg"),
        "btnDangerHover":      v("danger_button_hover"),
        "loginTitleColor":     v("login_title_color"),
        "loginBtnColor":       v("login_button_color"),
        "loginBg":             v("login_bg_color"),
        "loginBoxBg":          v("login_box_bg"),
    }


# ---------------------------------------------------------------------------
# Company helpers
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_default_company():
	"""Get the default company name for login page display."""
	try:
		defaults = frappe.defaults.get_defaults()
		default_company = defaults.get("company")

		if default_company:
			company_name = frappe.db.get_value(
				"Company", default_company, "company_name"
			)
			if company_name:
				return {"company_name": company_name}

		# Fallback — first company in the system
		companies = frappe.get_all("Company", fields=["company_name"], limit=1)
		if companies:
			return {"company_name": companies[0].company_name}

	except Exception:
		pass

	return {"company_name": "NBS"}