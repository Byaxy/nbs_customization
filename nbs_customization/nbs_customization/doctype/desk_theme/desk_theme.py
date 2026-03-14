# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

CACHE_KEY = "nbs_desk_theme"

# Default NBS theme values — matches :root defaults in nbs_theme.css
NBS_DEFAULTS = {
	"primary_color":                       "#001b52",
	"primary_hover":                       "#001540",
	"danger_color":                        "#dc2626",
	"danger_hover":                        "#b91c1c",
	"sidebar_background":                  "#e8e9e9",
	"sidebar_text_color":                  "#001b52",
	"active_item_background":              "#001b52",
	"active_item_text":                    "#00fdff",
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
	"login_title":                         "NBS",
	"login_title_color":                   "#001b52",
	"login_button_color":                  "#001b52",
	"login_bg_color":                      "#f1f5f9",
	"login_box_bg":                        "#ffffff",
}


class DeskTheme(Document):

	def on_update(self):
		"""Clear theme cache and notify all connected clients on save."""
		frappe.cache().delete_key(CACHE_KEY)
		frappe.publish_realtime(
			"nbs_theme_updated",
			message={"reload": True},
		)

	@frappe.whitelist()
	def reset_to_defaults(self):
		"""Reset all color fields to the NBS default values."""
		for fieldname, value in NBS_DEFAULTS.items():
			self.set(fieldname, value)
		self.save()
		frappe.cache().delete_key(CACHE_KEY)