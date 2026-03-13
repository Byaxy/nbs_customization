# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _

CACHE_KEY = "nbs_desk_theme"

NBS_DEFAULTS = {
	"primary_color":                       "#001b52",
	"primary_hover":                       "#001540",
	"accent_color":                        "#06b6d4",
	"danger_color":                        "#dc2626",
	"danger_hover":                        "#b91c1c",
	"sidebar_background":                  "#001b52",
	"sidebar_text_color":                  "#e2e8f0",
	"active_item_background":              "#06b6d4",
	"active_item_text":                    "#ffffff",
	"navbar_background":                   "#001b52",
	"navbar_text_color":                   "#ffffff",
	"navbar_icon_color":                   "#ffffff",
	"header_background":                   "#001b52",
	"header_text":                         "#ffffff",
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
	"form_background":                     "#ffffff",
	"input_border_color":                  "#cbd5e1",
	"input_focus_color":                   "#06b6d4",
	"label_color":                         "#475569",
	"login_title":                         "NBS",
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
	"""
	Return the active Desk Theme config as a flat dict of CSS-variable-ready
	values. Results are cached in Redis with a 24-hour TTL and are busted
	whenever the Desk Theme document is saved (via DeskTheme.on_update).
	Called from nbs_theme.js as: nbs_customization.api.get_desk_theme
	"""
	cached = frappe.cache().get_value(CACHE_KEY)
	if cached:
		return cached

	# get_singles_dict returns a plain dict of whatever is saved in the
	# SingleValue table — it never raises "not found", just returns an
	# empty dict if no values have been saved yet.
	saved = frappe.db.get_singles_dict("Desk Theme") or {}

	config = _build_config(saved)
	frappe.cache().set_value(CACHE_KEY, config, expires_in_sec=86400)
	return config


def _build_config(saved):
	"""
	Build the JS-facing config dict from a plain dict of saved values
	(from frappe.db.get_singles_dict). Falls back to NBS_DEFAULTS for
	any field that hasn't been saved yet.
	Each key maps 1-to-1 to a CSS variable declared in nbs_theme.css.
	"""
	def v(fieldname):
		return saved.get(fieldname) or NBS_DEFAULTS.get(fieldname, "")

	return {
		# Brand
		"primaryColor":        v("primary_color"),
		"primaryHover":        v("primary_hover"),
		"accentColor":         v("accent_color"),
		"dangerColor":         v("danger_color"),
		"dangerHover":         v("danger_hover"),

		# Sidebar
		"sidebarBg":           v("sidebar_background"),
		"sidebarText":         v("sidebar_text_color"),
		"sidebarActiveItemBg": v("active_item_background"),
		"sidebarActiveText":   v("active_item_text"),

		# Navbar
		"navbarBg":            v("navbar_background"),
		"navbarText":          v("navbar_text_color"),
		"navbarIcon":          v("navbar_icon_color"),

		# Tables & lists
		"tableHeaderBg":       v("header_background"),
		"tableHeaderText":     v("header_text"),
		"tableEvenBg":         v("even_row_background"),
		"tableRowHoverBg":     v("table_row_hover_background"),
		"selectRowHoverBg":    v("selectdropdown_row_hover_background"),

		# Child tables
		"childHeaderBg":       v("child_table_header_background"),
		"childHeaderText":     v("child_table_header_text"),

		# Buttons
		"btnPrimaryBg":        v("primary_button_bg"),
		"btnPrimaryHover":     v("primary_button_hover"),
		"btnPrimaryText":      v("primary_button_text"),
		"btnDangerBg":         v("danger_button_bg"),
		"btnDangerHover":      v("danger_button_hover"),

		# Forms & inputs
		"formBg":              v("form_background"),
		"inputBorder":         v("input_border_color"),
		"inputFocus":          v("input_focus_color"),
		"labelColor":          v("label_color"),

		# Login
		"loginTitle":          v("login_title"),
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