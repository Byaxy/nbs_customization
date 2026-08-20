import frappe
import json


def fix_children_order(node):
	"""Recursively fix children order in the print_designer_print_format tree."""
	if isinstance(node, dict):
		children = node.get("childrens", [])
		if children:
			if node.get("layoutType") == "row":
				children.sort(key=lambda c: float(c.get("startX", 0) or 0))
			elif node.get("layoutType") == "column":
				children.sort(key=lambda c: float(c.get("startY", 0) or 0))
			for child in children:
				fix_children_order(child)
	elif isinstance(node, list):
		for item in node:
			fix_children_order(item)


def validate_print_format(doc, method=None):
	if not hasattr(doc, "print_designer") or not doc.print_designer:
		return
	if not hasattr(doc, "print_designer_print_format") or not doc.print_designer_print_format:
		return
	tree = frappe.parse_json(doc.print_designer_print_format)

	for section in ["header", "body", "footer"]:
		sec_data = tree.get(section) if isinstance(tree, dict) else None
		if sec_data:
			if isinstance(sec_data, list):
				for page in sec_data:
					fix_children_order(page)
			elif isinstance(sec_data, dict):
				for page_list in sec_data.values():
					if isinstance(page_list, list):
						for page in page_list:
							fix_children_order(page)

	doc.print_designer_print_format = frappe.as_json(tree)


def fix_print_format(print_format_name):
	pf = frappe.get_doc("Print Format", print_format_name)
	tree = frappe.parse_json(pf.print_designer_print_format)

	for section in ["header", "body", "footer"]:
		sec_data = tree.get(section)
		if isinstance(sec_data, list):
			for page in sec_data:
				fix_children_order(page)
		elif isinstance(sec_data, dict):
			for page_list in sec_data.values():
				if isinstance(page_list, list):
					for page in page_list:
						fix_children_order(page)

	pf.print_designer_print_format = json.dumps(tree)
	pf.save(ignore_permissions=True)
	frappe.db.commit()
	return f"Fixed layout for {print_format_name}"


if __name__ == "__main__":
	import sys

	name = sys.argv[1] if len(sys.argv) > 1 else "Sales Invoice demo"
	print(fix_print_format(name))
