# Central test-record guard for the live site (see hooks.py before_tests).
# Marks every NBS Customization doctype as already-loaded so IntegrationTestCase
# skips the ERPNext test-record bootstrap, whose import-time master-data insert
# collides with live-site data (e.g. customized Standard Buying). No-op on fresh
# sites: our doctypes define no test_records, so skipping changes nothing there.
# Bypassed only by --skip-before-tests; placement suites keep their own guard too.

import frappe


def before_tests():
	for name in frappe.get_all("DocType", filters={"module": "NBS Customization"}, pluck="name"):
		frappe.local.test_objects[name] = []
