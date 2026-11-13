# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""Link submitted historical sales documents to a placement contract."""

import frappe
from frappe import _

from nbs_customization.utils.placement.dates import validate_not_future
from nbs_customization.utils.placement.historical_link_candidates import (
	DOCUMENT_CONFIG,
	INTERNAL_ITEM_TYPES,
	INTERNAL_TYPES,
	PUBLIC_TYPES_BY_CONTRACT,
	contract_item_data,
	get_internal_type,
	get_sales_order_candidates,
	suggest_document_type,
)
from nbs_customization.utils.placement.permissions import (
	require_contract_access,
	require_doc_access,
	require_roles,
)
from nbs_customization.utils.placement.progress import update_contract_progress
from nbs_customization.utils.placement.recovery import (
	RECOVERABLE_TRANSACTION_TYPES,
	recompute_contract_recovery,
)

LINK_ROLES = ("System Manager", "Placement Manager", "Accounts Manager")
OPEN_CONTRACT_STATUSES = {"Active", "Ownership Pending", "Fulfilled"}


@frappe.whitelist()
def get_linkable_sales_orders(contract, search=None):
	contract_doc = _get_contract(contract)
	return get_sales_order_candidates(contract_doc, search)


@frappe.whitelist()
def link_historical_sales_orders(contract, sales_orders):
	contract_doc = _get_contract(contract)
	_validate_open_contract(contract_doc)
	prepared = _prepare_rows(contract_doc, sales_orders)

	linked_sales_orders = 0
	linked_sales_invoices = 0
	linked_delivery_notes = 0
	for row in prepared:
		doc = row["doc"]
		values = {
			"custom_instrument_placement_contract": contract_doc.name,
			"custom_placement_transaction_type": row["transaction_type"],
		}
		if doc.doctype == "Sales Invoice":
			values["custom_counts_toward_recovery"] = (
				1 if row["transaction_type"] in RECOVERABLE_TRANSACTION_TYPES else 0
			)
		frappe.db.set_value(doc.doctype, doc.name, values)
		doc.add_comment(
			"Comment",
			_("Linked to Placement Contract {0} as {1}.").format(
				frappe.bold(contract_doc.name), frappe.bold(row["transaction_type"])
			),
		)
		if doc.doctype == "Sales Order":
			linked_sales_orders += 1
		elif doc.doctype == "Sales Invoice":
			linked_sales_invoices += 1
		else:
			linked_delivery_notes += 1

	if prepared:
		recompute_contract_recovery(contract_doc.name)
		update_contract_progress(contract_doc.name)
		contract_doc.add_comment(
			"Comment",
			_(
				"Linked {0} historical transaction(s): {1} sales order(s), {2} sales invoice(s), {3} delivery note(s)."
			).format(len(prepared), linked_sales_orders, linked_sales_invoices, linked_delivery_notes),
		)

	return {
		"sales_orders": linked_sales_orders,
		"sales_invoices": linked_sales_invoices,
		"delivery_notes": linked_delivery_notes,
		"total": linked_sales_orders + linked_sales_invoices + linked_delivery_notes,
	}


def _get_contract(contract):
	require_roles(*LINK_ROLES)
	require_contract_access(contract)
	return frappe.get_doc("Instrument Placement Contract", contract)


def _validate_open_contract(contract):
	if contract.docstatus != 1:
		frappe.throw(_("Placement Contract {0} is not submitted.").format(frappe.bold(contract.name)))
	if contract.contract_status not in OPEN_CONTRACT_STATUSES:
		frappe.throw(
			_("Placement Contract {0} cannot be linked while its status is {1}.").format(
				frappe.bold(contract.name), frappe.bold(contract.contract_status)
			)
		)


def _prepare_rows(contract, sales_orders):
	names = _parse_sales_orders(sales_orders)
	prepared = []
	seen = set()
	for name in names:
		doc = frappe.get_doc("Sales Order", name)
		transaction_type = suggest_document_type(contract, doc)
		_validate_link(contract, doc, transaction_type)
		_add_prepared(prepared, seen, contract, doc, transaction_type)

		for linked_doc in _get_linked_documents(contract, doc):
			linked_type = suggest_document_type(contract, linked_doc) or transaction_type
			_validate_link(contract, linked_doc, linked_type)
			_add_prepared(prepared, seen, contract, linked_doc, linked_type)
	return prepared


def _parse_sales_orders(sales_orders):
	if isinstance(sales_orders, str):
		sales_orders = frappe.parse_json(sales_orders)
	if not isinstance(sales_orders, (list, tuple)) or not sales_orders:
		frappe.throw(_("Select at least one Sales Order to link."))

	names = []
	for entry in sales_orders:
		name = entry if isinstance(entry, str) else entry.get("name")
		if not name:
			frappe.throw(_("Invalid Sales Order row."))
		names.append(name)
	return names


def _add_prepared(prepared, seen, contract, doc, transaction_type):
	key = (doc.doctype, doc.name)
	if key in seen:
		return
	seen.add(key)
	if _already_linked(contract, doc, transaction_type):
		return
	prepared.append(
		{
			"doc": doc,
			"transaction_type": transaction_type,
		}
	)


def _already_linked(contract, doc, transaction_type):
	return (
		doc.get("custom_instrument_placement_contract") == contract.name
		and doc.get("custom_placement_transaction_type") == transaction_type
	)


def _validate_link(contract, doc, transaction_type):
	if not transaction_type:
		frappe.throw(
			_("Transaction Type could not be detected for {0} {1}.").format(
				frappe.bold(doc.doctype), frappe.bold(doc.name)
			)
		)
	require_doc_access(doc.doctype, doc.name, "write")
	if doc.docstatus != 1:
		frappe.throw(_("{0} {1} is not submitted.").format(frappe.bold(doc.doctype), frappe.bold(doc.name)))
	if doc.customer != contract.customer:
		frappe.throw(
			_("{0} {1} belongs to customer {2}, not contract customer {3}.").format(
				frappe.bold(doc.doctype),
				frappe.bold(doc.name),
				frappe.bold(doc.customer),
				frappe.bold(contract.customer),
			)
		)

	current_contract = doc.get("custom_instrument_placement_contract")
	if current_contract and current_contract != contract.name:
		frappe.throw(
			_("{0} {1} is already linked to Placement Contract {2}.").format(
				frappe.bold(doc.doctype), frappe.bold(doc.name), frappe.bold(current_contract)
			)
		)
	if _already_linked(contract, doc, transaction_type):
		return
	current_type = doc.get("custom_placement_transaction_type")
	if current_contract == contract.name and current_type and current_type != transaction_type:
		frappe.throw(
			_("{0} {1} is already linked as {2}.").format(
				frappe.bold(doc.doctype), frappe.bold(doc.name), frappe.bold(current_type)
			)
		)

	date_field = DOCUMENT_CONFIG[doc.doctype]["date_field"]
	validate_not_future(doc.get(date_field), doc.meta.get_label(date_field))
	_validate_document_transaction_type(contract, doc, transaction_type)
	_validate_item_membership(contract, doc)


def _validate_document_transaction_type(contract, doc, transaction_type):
	internal_type = get_internal_type(contract, [row.item_code for row in doc.get("items", [])])
	if transaction_type in INTERNAL_TYPES:
		if internal_type == transaction_type:
			return
		frappe.throw(
			_("Transaction type {0} is not valid for {1}.").format(
				frappe.bold(transaction_type), frappe.bold(doc.name)
			)
		)

	if contract.contract_type == "CPT" and transaction_type == "Contract Reagent Sale":
		if internal_type == "Contract Reagent Sale":
			return
		frappe.throw(
			_("CPT fee invoices must contain the revenue share fee item to use Contract Reagent Sale.")
		)

	allowed = PUBLIC_TYPES_BY_CONTRACT.get(contract.contract_type, set())
	if transaction_type not in allowed:
		frappe.throw(
			_("Transaction type {0} is not valid for {1} contracts.").format(
				frappe.bold(transaction_type), frappe.bold(contract.contract_type)
			)
		)


def _validate_item_membership(contract, doc):
	reagent_codes, consumable_codes, _price_by_code = contract_item_data(contract)
	allowed = reagent_codes | consumable_codes | set(INTERNAL_ITEM_TYPES) | {contract.analyzer_pid}
	for row in doc.get("items", []):
		if row.item_code and row.item_code not in allowed:
			frappe.throw(
				_("Item {0} is not valid for Contract {1}.").format(
					frappe.bold(row.item_code), frappe.bold(contract.name)
				)
			)


def _get_linked_documents(contract, sales_order):
	documents = []
	for doctype, child_doctype, link_field in (
		("Sales Invoice", "Sales Invoice Item", "sales_order"),
		("Delivery Note", "Delivery Note Item", "against_sales_order"),
	):
		names = frappe.get_all(
			child_doctype,
			filters={link_field: sales_order.name, "parenttype": doctype},
			pluck="parent",
		)
		for name in sorted(set(names)):
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus != 1 or doc.get("is_return"):
				continue
			documents.append(doc)
	return documents
