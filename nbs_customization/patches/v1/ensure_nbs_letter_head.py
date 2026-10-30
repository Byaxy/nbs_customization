import frappe

LETTER_HEAD = "Company Letter Head"
ERPNEXT_DEFAULTS = ("Company Letterhead", "Company Letterhead - Grey")


def execute():
	content = _read_template("letterhead.html")
	footer = _read_template("letterhead_footer.html")

	if frappe.db.exists("Letter Head", LETTER_HEAD):
		_ensure_footer(footer)
		return

	current_default = frappe.db.get_value("Letter Head", {"is_default": 1}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Letter Head",
			"letter_head_name": LETTER_HEAD,
			"source": "HTML",
			"content": content,
			"footer_source": "HTML",
			"footer": footer,
			"is_default": 1 if current_default in (None, *ERPNEXT_DEFAULTS) else 0,
			"disabled": 0,
		}
	)
	doc.insert(ignore_permissions=True)


def _read_template(name):
	return frappe.read_file(frappe.get_app_path("nbs_customization", "templates", "print_formats", name))


def _ensure_footer(footer):
	doc = frappe.get_doc("Letter Head", LETTER_HEAD)
	if doc.footer:
		return
	doc.footer_source = "HTML"
	doc.footer = footer
	doc.save(ignore_permissions=True)
