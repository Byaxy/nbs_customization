# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Date guards shared by placement transactions."""

import frappe
from frappe.utils import getdate, nowdate


def validate_not_future(value, label):
	if value and getdate(value) > getdate(nowdate()):
		frappe.throw(
			frappe._("{0} cannot be a future date.").format(frappe.bold(label)),
			title=frappe._("Future Date Not Allowed"),
		)
