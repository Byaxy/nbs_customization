# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import calendar
import datetime
import re

import frappe
from frappe.utils import getdate, today

PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validate_period(period):
	if not isinstance(period, str) or not PERIOD_PATTERN.match(period):
		frappe.throw(frappe._("Period must use the YYYY-MM format."))
	return period


def period_start(period):
	validate_period(period)
	year, month = period.split("-")
	return datetime.date(int(year), int(month), 1)


def period_end(period):
	start = period_start(period)
	last_day = calendar.monthrange(start.year, start.month)[1]
	return datetime.date(start.year, start.month, last_day)


def posting_date_for_period(period):
	"""Use the period end for past periods, but never post in the future."""
	return min(getdate(today()), period_end(period))
