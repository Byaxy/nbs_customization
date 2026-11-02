import frappe

LEGACY_SIDEBAR = "NBS Customization"
LEGACY_MERGED_FROM = [LEGACY_SIDEBAR]


def execute():
	_delete_workspace_sidebar()
	_delete_converted_sidebar()
	frappe.db.commit()
	frappe.clear_cache()


def _delete_workspace_sidebar():
	if not frappe.db.exists("DocType", "Workspace Sidebar"):
		return
	if not frappe.db.exists("Workspace Sidebar", LEGACY_SIDEBAR):
		return

	frappe.delete_doc(
		"Workspace Sidebar",
		LEGACY_SIDEBAR,
		force=True,
		ignore_permissions=True,
		ignore_missing=True,
	)


def _delete_converted_sidebar():
	sidebar = frappe.db.get_value(
		"Sidebar",
		LEGACY_SIDEBAR,
		["module", "standard", "app", "merged_from"],
		as_dict=True,
	)
	if not sidebar:
		return
	if sidebar.module != LEGACY_SIDEBAR or sidebar.standard or sidebar.app:
		return
	if _merged_from(sidebar.merged_from) != LEGACY_MERGED_FROM:
		return

	frappe.delete_doc(
		"Sidebar",
		LEGACY_SIDEBAR,
		force=True,
		ignore_permissions=True,
		ignore_missing=True,
	)


def _merged_from(value):
	try:
		sources = frappe.parse_json(value or "[]")
	except TypeError, ValueError:
		return []
	return sources if isinstance(sources, list) else []
