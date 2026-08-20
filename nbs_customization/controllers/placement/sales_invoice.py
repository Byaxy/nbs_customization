# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


def validate(doc, method=None):
	from nbs_customization.controllers.placement.sales_validate import validate_placement_transaction
	validate_placement_transaction(doc)


def on_submit(doc, method=None):
	if doc.get("custom_instrument_placement_contract") and doc.get("custom_counts_toward_recovery"):
		recompute_contract_recovery(doc.custom_instrument_placement_contract)


def on_cancel(doc, method=None):
	if doc.get("custom_instrument_placement_contract") and doc.get("custom_counts_toward_recovery"):
		recompute_contract_recovery(doc.custom_instrument_placement_contract)
