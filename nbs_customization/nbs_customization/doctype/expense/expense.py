# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from nbs_customization.controllers.check_clearing import get_check_mop, validate_destination_account


class Expense(Document):
	def validate(self):
		self._set_company_defaults()
		self._resolve_payment_account()
		self._resolve_paid_to()
		self._set_account_currencies()
		self._validate_category_required()
		self._validate_accompanying()
		self._validate_invoice_link()
		self._validate_check_or_bank_reference()

	def on_submit(self):
		if self.payment_type == "Direct Payment":
			self._create_journal_entry()
		else:
			self._create_payment_entry()

	def on_cancel(self):
		self._cancel_clearing_journal_entry()
		self._cancel_or_delete_lcv()
		if self.payment_type == "Direct Payment":
			self._reverse_journal_entry()
		else:
			self._reverse_payment_entry()

	def _cancel_clearing_journal_entry(self):
		# If a check was cleared, the clearing JE must be cancelled before the underlying doc
		if not self.get("clearing_journal_entry"):
			return
		# Break circular link first
		frappe.db.set_value("Expense", self.name, "clearing_journal_entry", None, update_modified=False)
		je_name = self.clearing_journal_entry
		if je_name and frappe.db.exists("Journal Entry", je_name):
			je = frappe.get_doc("Journal Entry", je_name)
			if je.docstatus == 1:
				je.cancel()

	# ------------------------------------------------------------------ #
	# Validation helpers                                                   #
	# ------------------------------------------------------------------ #

	def _set_company_defaults(self):
		if not self.company:
			self.company = frappe.defaults.get_user_default("Company")
		if not self.cost_center:
			self.cost_center = frappe.db.get_value("Company", self.company, "cost_center")

	def _resolve_payment_account(self):
		"""
		Resolve the paying account from the Payment Method, mirroring Payment Entry.
		A manual override of paid_from is respected.
		"""
		if not self.mode_of_payment:
			return

		if not self.paid_from:
			from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
				get_bank_cash_account,
			)

			self.paid_from = get_bank_cash_account(self.mode_of_payment, self.company)["account"]

	def _resolve_paid_to(self):
		"""
		Sets the read-only 'paid to' account based on the payment flow:
		- Against Purchase Invoice → the supplier's payable account.
		- Direct Payment → the expense account of the category (debit side).
		"""
		if self.payment_type == "Against Purchase Invoice" and self.purchase_invoice:
			pi = frappe.db.get_value(
				"Purchase Invoice",
				self.purchase_invoice,
				["supplier", "company"],
				as_dict=True,
			)
			if pi and pi.supplier:
				from erpnext.accounts.party import get_party_account

				self.paid_to = get_party_account("Supplier", pi.supplier, self.company or pi.company)
		else:
			self.paid_to = frappe.db.get_value("Expense Category", self.expense_category, "expense_account")

	def _set_account_currencies(self):
		self.paid_from_account_currency = (
			frappe.db.get_value("Account", self.paid_from, "account_currency") if self.paid_from else None
		)
		self.paid_to_account_currency = (
			frappe.db.get_value("Account", self.paid_to, "account_currency") if self.paid_to else None
		)

	def _validate_category_required(self):
		needs_category = self.payment_type == "Direct Payment" or self.is_accompanying
		if needs_category and not self.expense_category:
			frappe.throw(_("Expense Category is required."))

	def _validate_accompanying(self):
		if not self.is_accompanying:
			# Non-accompanying: clear shipment fields, validate category
			self.expense_scope = None
			self.linked_shipment = None
			self.linked_purchase = None
			self.linked_purchase_order = None
			self.landed_cost_voucher = None

			is_acc_cat = frappe.db.get_value(
				"Expense Category", self.expense_category, "is_accompanying_expense"
			)
			if is_acc_cat:
				frappe.throw(
					_(
						f"The Expense Category <b>{self.expense_category}</b> is marked "
						f"as an Accompanying Expense Category. Either use a non-accompanying "
						f"category or check <b>Is Accompanying Expense</b> on this expense."
					)
				)
			self._validate_expense_account_type(must_be_valuation=False)
			return

		# --- is_accompanying = True ---
		scope = self.expense_scope or "Single Purchase Order"

		# Validate category is accompanying
		is_acc_cat = frappe.db.get_value("Expense Category", self.expense_category, "is_accompanying_expense")
		if not is_acc_cat:
			frappe.throw(
				_(
					f"The Expense Category <b>{self.expense_category}</b> is not marked "
					f"as an Accompanying Expense Category. Please use a category with "
					f"<b>Is Accompanying Expense Category</b> checked."
				)
			)
		self._validate_expense_account_type(must_be_valuation=True)

		if self.payment_type == "Against Purchase Invoice" and self.purchase_invoice:
			self._validate_pi_category_account_match()

		if scope == "Single Purchase Order":
			self.linked_purchase = None
			self.linked_shipment = None
			if not self.linked_purchase_order:
				frappe.throw(_("Linked Purchase Order is required for accompanying expenses."))
			po = frappe.db.get_value(
				"Purchase Order",
				self.linked_purchase_order,
				["company", "docstatus", "status"],
				as_dict=True,
			)
			if not po:
				frappe.throw(_(f"Purchase Order <b>{self.linked_purchase_order}</b> not found."))
			if po.docstatus != 1:
				frappe.throw(
					_(
						f"Purchase Order <b>{self.linked_purchase_order}</b> must be submitted "
						f"before linking it to an expense."
					)
				)
			if po.company != self.company:
				frappe.throw(
					_(
						f"Purchase Order <b>{self.linked_purchase_order}</b> belongs to "
						f"company <b>{po.company}</b>, not <b>{self.company}</b>."
					)
				)

		elif scope == "Single Purchase Receipt":
			# Legacy scope kept so cancels/amends of pre-migration documents still validate.
			self.linked_shipment = None
			self.linked_purchase_order = None
			if not self.linked_purchase:
				frappe.throw(_("Linked Purchase Receipt is required for accompanying expenses."))
			# Validate PR belongs to same company
			pr_company = frappe.db.get_value("Purchase Receipt", self.linked_purchase, "company")
			if pr_company and pr_company != self.company:
				frappe.throw(
					_(
						f"Purchase Receipt <b>{self.linked_purchase}</b> belongs to "
						f"company <b>{pr_company}</b>, not <b>{self.company}</b>."
					)
				)

		elif scope == "Inbound Shipment":
			self.linked_purchase = None
			self.linked_purchase_order = None
			if not self.linked_shipment:
				frappe.throw(
					_("Linked Inbound Shipment is required when Expense Scope is 'Inbound Shipment'.")
				)

			ship = frappe.db.get_value(
				"Inbound Shipment",
				self.linked_shipment,
				["company", "docstatus", "shipment_status"],
				as_dict=True,
			)
			if not ship:
				frappe.throw(_(f"Inbound Shipment <b>{self.linked_shipment}</b> not found."))
			if ship.docstatus != 1:
				frappe.throw(
					_(
						f"Inbound Shipment <b>{self.linked_shipment}</b> must be submitted "
						f"before linking it to an expense."
					)
				)
			if ship.company != self.company:
				frappe.throw(
					_(
						f"Inbound Shipment <b>{self.linked_shipment}</b> belongs to "
						f"company <b>{ship.company}</b>, not <b>{self.company}</b>."
					)
				)

	def _validate_pi_category_account_match(self):
		message = get_pi_category_account_mismatch(self)
		if message:
			frappe.throw(message)

	def _validate_expense_account_type(self, must_be_valuation: bool):
		expense_account = frappe.db.get_value("Expense Category", self.expense_category, "expense_account")
		if not expense_account:
			return
		account_type = frappe.db.get_value("Account", expense_account, "account_type")
		if must_be_valuation and account_type != "Expenses Included In Valuation":
			frappe.throw(
				_(
					f"The Expense Account <b>{expense_account}</b> for category "
					f"<b>{self.expense_category}</b> must have Account Type "
					f"<b>'Expenses Included In Valuation'</b> for accompanying expenses. "
					f"Current type: <b>{account_type or 'None'}</b>."
				)
			)
		if not must_be_valuation and account_type == "Expenses Included In Valuation":
			frappe.throw(
				_(
					f"The Expense Account <b>{expense_account}</b> for category "
					f"<b>{self.expense_category}</b> must NOT have Account Type "
					f"<b>'Expenses Included In Valuation'</b> for non-accompanying expenses."
				)
			)

	def _validate_invoice_link(self):
		"""Validates the linked Purchase Invoice for Flow B."""
		if self.payment_type != "Against Purchase Invoice":
			self.purchase_invoice = None
			return
		if not self.purchase_invoice:
			frappe.throw("Purchase Invoice is required for Against Purchase Invoice payment type.")

		pi = frappe.db.get_value(
			"Purchase Invoice",
			self.purchase_invoice,
			["docstatus", "outstanding_amount", "company", "supplier"],
			as_dict=True,
		)

		if not pi:
			frappe.throw(f"Purchase Invoice {self.purchase_invoice} not found.")

		if pi.docstatus != 1:
			frappe.throw(
				f"Purchase Invoice <b>{self.purchase_invoice}</b> must be submitted before it can be paid."
			)

		if pi.outstanding_amount <= 0:
			frappe.throw(
				f"Purchase Invoice <b>{self.purchase_invoice}</b> has no outstanding "
				f"amount. It may already be fully paid."
			)

		if pi.company != self.company:
			frappe.throw(
				f"Purchase Invoice <b>{self.purchase_invoice}</b> belongs to company "
				f"<b>{pi.company}</b> but this expense is for <b>{self.company}</b>."
			)

		# Auto-set amount from invoice outstanding if not set
		if not self.amount:
			self.amount = pi.outstanding_amount

	def _validate_check_or_bank_reference(self):
		"""
		Reference No/Date mandatory for Bank *or* Check mode.
		For Check also routes paid_from to the outward clearing account and
		defaults clearing_destination_account. clearance_date is NOT required
		here — only at clearing (dialog).
		"""
		mop = get_check_mop(self.mode_of_payment) if self.mode_of_payment else {}
		needs_check = bool(mop.get("is_check"))
		if needs_check:
			self.is_check = 1
			expected = mop.get("clearing_account_outward")
			if expected and self.paid_from != expected:
				self.paid_from = expected
			if not self.clearing_destination_account and mop.get("default_clearing_destination"):
				self.clearing_destination_account = mop.get("default_clearing_destination")

		needs_bank = False
		if self.paid_from:
			account_type = frappe.get_cached_value("Account", self.paid_from, "account_type")
			# clearing accounts have no account_type, so Bank check only matters for non-check
			if account_type == "Bank":
				needs_bank = True

		needs_ref = needs_bank or needs_check
		if needs_ref and (not self.reference_no or not self.reference_date):
			if needs_check:
				frappe.throw(_("Cheque/Reference No and Reference Date are mandatory for Check payments."))
			else:
				frappe.throw(_("Reference No and Reference Date is mandatory for Bank transaction"))

	def _validate_bank_reference(self):
		# Back-compat alias
		return self._validate_check_or_bank_reference()

	# ------------------------------------------------------------------ #
	# Flow A — Direct Payment via Journal Entry                           #
	# ------------------------------------------------------------------ #

	def _create_journal_entry(self):
		"""
		On submit: debit the expense category GL account,
		credit the paying account.
		"""
		expense_account = frappe.db.get_value("Expense Category", self.expense_category, "expense_account")
		if not expense_account:
			frappe.throw(
				f"No GL account configured for Expense Category: "
				f"<b>{self.expense_category}</b>. "
				f"Please set the Expense Account on the category."
			)

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.expense_date
		je.mode_of_payment = self.mode_of_payment
		je.cheque_no = self.reference_no
		je.cheque_date = self.reference_date
		je.user_remark = f"Expense: {self.name} — {self.expense_description} | Payee: {self.payee or 'N/A'}"

		# Debit — expense category GL account
		je.append(
			"accounts",
			{
				"account": expense_account,
				"debit_in_account_currency": self.amount,
				"credit_in_account_currency": 0,
				"cost_center": frappe.db.get_value("Company", je.company, "cost_center"),
			},
		)

		# Credit — paying account (cash/bank)
		je.append(
			"accounts",
			{
				"account": self.paid_from,
				"debit_in_account_currency": 0,
				"credit_in_account_currency": self.amount,
			},
		)

		je.insert(ignore_permissions=True)
		je.submit()

		# Store JE reference on this expense
		self.db_set("journal_entry", je.name)

	def _reverse_journal_entry(self):
		"""
		On cancel: cancel the linked Journal Entry.
		"""
		if not self.get("journal_entry"):
			return

		je = frappe.get_doc("Journal Entry", self.journal_entry)
		if je.docstatus == 1:
			je.cancel()

		self.db_set("journal_entry", None)

	# ------------------------------------------------------------------ #
	# Flow B — Against Purchase Invoice via Payment Entry                 #
	# ------------------------------------------------------------------ #

	def _create_payment_entry(self):
		"""
		Creates a Payment Entry to pay the linked Purchase Invoice.
		This is ERPNext-native and correctly reconciles AP.
		"""
		pi = frappe.get_doc("Purchase Invoice", self.purchase_invoice)

		# Guard: warn if currencies differ
		paid_from_currency = frappe.db.get_value("Account", self.paid_from, "account_currency")
		if pi.currency != paid_from_currency:
			frappe.throw(
				f"Currency mismatch: Purchase Invoice is in <b>{pi.currency}</b> "
				f"but Account Paid From is in <b>{paid_from_currency}</b>. "
				f"Multi-currency payments are not yet supported in this flow. "
				f"Please use a Payment Entry directly."
			)

		# Use ERPNext's built-in payment entry creation from invoice
		from erpnext.accounts.doctype.payment_entry.payment_entry import (
			get_payment_entry,
		)

		pe = get_payment_entry("Purchase Invoice", self.purchase_invoice)
		pe.posting_date = self.expense_date
		pe.paid_from = self.paid_from
		pe.paid_amount = self.amount
		pe.received_amount = self.amount
		pe.source_exchange_rate = 1
		pe.target_exchange_rate = 1
		pe.mode_of_payment = self.mode_of_payment
		pe.reference_no = self.reference_no
		# For Check, require explicit reference_date (no silent fallback)
		if self.is_check and not self.reference_date:
			frappe.throw(_("Reference Date is mandatory for Check payments."))
		pe.reference_date = self.reference_date or self.expense_date
		pe.remarks = (
			f"Payment via Expense {self.name} — {self.expense_description} "
			f"| Payee: {self.payee or pi.supplier}"
		)

		# Set the allocated amount on the reference row
		for ref in pe.references:
			if ref.reference_name == self.purchase_invoice:
				ref.allocated_amount = min(self.amount, ref.outstanding_amount)

		pe.insert(ignore_permissions=True)
		pe.submit()
		self.db_set("payment_entry", pe.name)

	def _reverse_payment_entry(self):
		if not self.get("payment_entry"):
			return
		pe = frappe.get_doc("Payment Entry", self.payment_entry)
		if pe.docstatus == 1:
			pe.cancel()
		self.db_set("payment_entry", None)

	# ------------------------------------------------------------------ #
	# LCV handling                                                        #
	# ------------------------------------------------------------------ #

	def _cancel_or_delete_lcv(self):
		"""
		On cancel: if an LCV was created for this accompanying expense,
		cancel it if submitted or delete it if still draft.
		"""
		if not self.get("landed_cost_voucher"):
			return

		if not frappe.db.exists("Landed Cost Voucher", self.landed_cost_voucher):
			self.db_set("landed_cost_voucher", None)
			return

		lcv = frappe.get_doc("Landed Cost Voucher", self.landed_cost_voucher)

		if lcv.docstatus == 1:
			# Submitted — cancel it
			lcv.cancel()
			frappe.msgprint(
				f"Landed Cost Voucher {self.landed_cost_voucher} has been cancelled.",
				indicator="orange",
				alert=True,
			)
		elif lcv.docstatus == 0:
			# Draft — delete it
			frappe.delete_doc("Landed Cost Voucher", self.landed_cost_voucher, ignore_permissions=True)
			frappe.msgprint(
				f"Landed Cost Voucher {self.landed_cost_voucher} has been deleted.",
				indicator="orange",
				alert=True,
			)

		self.db_set("landed_cost_voucher", None)


# ------------------------------------------------------------------ #
# Whitelisted helpers (called from JS)                                #
# ------------------------------------------------------------------ #


@frappe.whitelist()
def get_invoice_details(purchase_invoice):
	"""
	Returns key details of a Purchase Invoice for prefilling the Expense form.
	Called from JS when a Purchase Invoice is selected.
	"""
	pi = frappe.db.get_value(
		"Purchase Invoice",
		purchase_invoice,
		["outstanding_amount", "supplier", "supplier_name", "company", "bill_no", "docstatus"],
		as_dict=True,
	)
	if not pi:
		frappe.throw(f"Purchase Invoice {purchase_invoice} not found.")
	if pi.docstatus != 1:
		frappe.throw(f"Purchase Invoice {purchase_invoice} is not submitted.")
	if pi.outstanding_amount <= 0:
		frappe.throw(f"Purchase Invoice {purchase_invoice} has no outstanding amount.")
	return pi


@frappe.whitelist()
def get_purchase_invoices_search(doctype, txt, searchfield, start, page_len, filters):
	"""
	Custom Link-search for the Purchase Invoice field on the Expense form.
	Shows invoice no, supplier, grand total, outstanding amount and posting date
	in the dropdown, and excludes already-paid/cancelled invoices.
	"""
	company = (filters or {}).get("company")

	return frappe.db.sql(
		"""
		SELECT
			pi.name,
			pi.supplier_name,
			pi.grand_total,
			pi.outstanding_amount,
			pi.posting_date
		FROM `tabPurchase Invoice` pi
		WHERE pi.docstatus = 1
			AND pi.status NOT IN ('Paid', 'Cancelled')
			AND (%(company)s IS NULL OR pi.company = %(company)s)
			AND (
				pi.name LIKE %(txt)s
				OR IFNULL(pi.supplier_name, '') LIKE %(txt)s
				OR IFNULL(pi.bill_no, '') LIKE %(txt)s
			)
		ORDER BY pi.posting_date DESC, pi.name DESC
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"company": company,
			"txt": f"%{txt}%",
			"page_len": page_len,
			"start": start,
		},
	)


@frappe.whitelist()
def get_purchase_orders_search(doctype, txt, searchfield, start, page_len, filters):
	"""
	Custom Link-search for the Linked Purchase Order field on the Expense form.
	Shows order no, supplier, grand total and transaction date, and excludes
	cancelled orders.
	"""
	company = (filters or {}).get("company")

	return frappe.db.sql(
		"""
		SELECT
			po.name,
			po.supplier_name,
			po.grand_total,
			po.transaction_date
		FROM `tabPurchase Order` po
		WHERE po.docstatus = 1
			AND po.status != 'Cancelled'
			AND (%(company)s IS NULL OR po.company = %(company)s)
			AND (
				po.name LIKE %(txt)s
				OR IFNULL(po.supplier_name, '') LIKE %(txt)s
			)
		ORDER BY po.transaction_date DESC, po.name DESC
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"company": company,
			"txt": f"%{txt}%",
			"page_len": page_len,
			"start": start,
		},
	)


@frappe.whitelist()
def get_payment_method_account(mode_of_payment, company):
	"""
	Resolves the default Cash/Bank account for a Mode of Payment and Company,
	plus that account's currency. Mirrors Payment Entry's paid_from auto-fill.
	Also returns check-mode metadata for client-side required toggling.
	"""
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
		get_bank_cash_account,
	)

	account = get_bank_cash_account(mode_of_payment, company)["account"]
	account_currency = frappe.db.get_value("Account", account, "account_currency")
	mop = get_check_mop(mode_of_payment)
	return {
		"account": account,
		"account_currency": account_currency,
		"is_check": bool(mop.get("is_check")),
		"clearing_account_outward": mop.get("clearing_account_outward"),
		"default_clearing_destination": mop.get("default_clearing_destination"),
	}


@frappe.whitelist()
def get_supplier_payable_details(supplier, company):
	"""
	Returns the payable account and its currency for a Supplier in a Company.
	Used to prefill 'Account Paid To' on the Against Purchase Invoice flow.
	"""
	from erpnext.accounts.party import get_party_account

	payable_account = get_party_account("Supplier", supplier, company)
	account_currency = frappe.db.get_value("Account", payable_account, "account_currency")
	return {"paid_to": payable_account, "account_currency": account_currency}


@frappe.whitelist()
def check_shipment_fully_received(shipment_name):
	"""
	Checks whether all items in the shipment's package_items have been
	fully received in submitted PRs tagged to this shipment via the
	inbound_shipment field on Purchase Receipt.
	"""
	shipment_items = frappe.db.sql(
		"""
		SELECT
			purchase_order,
			item_code,
			SUM(qty) AS expected_qty
		FROM `tabInbound Shipment Package Item`
		WHERE parent       = %(shipment)s
		AND purchase_order IS NOT NULL AND purchase_order != ''
		AND item_code      IS NOT NULL AND item_code      != ''
		GROUP BY purchase_order, item_code
		""",
		{"shipment": shipment_name},
		as_dict=True,
	)

	if not shipment_items:
		return {
			"ready": False,
			"message": "No package items with Purchase Order references found on this shipment.",
			"unreceived_items": [],
		}

	unreceived = []

	for row in shipment_items:
		result = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(pri.qty), 0)
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pr.custom_inbound_shipment = %(shipment)s
			AND pri.purchase_order  = %(po)s
			AND pri.item_code       = %(item_code)s
			AND pr.docstatus        = 1
			""",
			{
				"shipment": shipment_name,
				"po": row.purchase_order,
				"item_code": row.item_code,
			},
		)

		received_qty = flt(result[0][0]) if result else 0.0
		expected = flt(row.expected_qty)

		if received_qty < expected:
			unreceived.append(
				{
					"purchase_order": row.purchase_order,
					"item_code": row.item_code,
					"expected_qty": expected,
					"received_qty": received_qty,
					"pending_qty": flt(expected - received_qty, 3),
				}
			)

	if unreceived:
		lines = "".join(
			[
				f"<li><b>{r['item_code']}</b> from <b>{r['purchase_order']}</b> — "
				f"expected {r['expected_qty']}, received {r['received_qty']}, "
				f"pending {r['pending_qty']}</li>"
				for r in unreceived
			]
		)
		message = (
			f"The following items have not been fully received for this shipment:<br>"
			f"<ul>{lines}</ul>"
			f"All shipment items must be received before creating a Landed Cost Voucher."
		)
	else:
		message = None

	return {
		"ready": len(unreceived) == 0,
		"unreceived_items": unreceived,
		"message": message,
	}


@frappe.whitelist()
def check_purchase_order_fully_received(po_name):
	"""
	Checks whether every item on a Purchase Order has been fully received in
	submitted Purchase Receipts. Mirrors check_shipment_fully_received.
	"""
	po = frappe.db.get_value(
		"Purchase Order",
		po_name,
		["docstatus", "status"],
		as_dict=True,
	)
	if not po:
		frappe.throw(_(f"Purchase Order <b>{po_name}</b> not found."))
	if po.docstatus != 1:
		return {
			"ready": False,
			"message": f"Purchase Order <b>{po_name}</b> is not submitted.",
			"unreceived_items": [],
		}

	po_items = frappe.db.sql(
		"""
		SELECT item_code, qty, received_qty
		FROM `tabPurchase Order Item`
		WHERE parent = %(po)s
		""",
		{"po": po_name},
		as_dict=True,
	)

	if not po_items:
		return {
			"ready": False,
			"message": f"Purchase Order <b>{po_name}</b> has no items.",
			"unreceived_items": [],
		}

	unreceived = []
	for row in po_items:
		expected = flt(row.qty)
		received = flt(row.received_qty)
		if received + 0.005 < expected:
			unreceived.append(
				{
					"purchase_order": po_name,
					"item_code": row.item_code,
					"expected_qty": expected,
					"received_qty": received,
					"pending_qty": flt(expected - received, 3),
				}
			)

	if unreceived:
		lines = "".join(
			[
				f"<li><b>{r['item_code']}</b> — ordered {r['expected_qty']}, "
				f"received {r['received_qty']}, pending {r['pending_qty']}</li>"
				for r in unreceived
			]
		)
		message = (
			f"The following items on Purchase Order <b>{po_name}</b> have not been "
			f"fully received:<br><ul>{lines}</ul>"
			f"All items must be received before creating a Landed Cost Voucher."
		)
	else:
		message = None

	return {
		"ready": len(unreceived) == 0,
		"unreceived_items": unreceived,
		"message": message,
	}


def get_prs_from_po(po_name):
	"""
	Returns all submitted, non-return Purchase Receipts that reference the given
	Purchase Order, as [{"receipt_document", "supplier", "grand_total"}].
	"""
	return frappe.db.sql(
		"""
		SELECT DISTINCT
			pr.name AS receipt_document,
			pr.supplier,
			pr.grand_total
		FROM `tabPurchase Receipt` pr
		WHERE pr.docstatus = 1
			AND pr.is_return = 0
			AND EXISTS (
				SELECT 1 FROM `tabPurchase Receipt Item` pri
				WHERE pri.parent = pr.name
				AND pri.purchase_order = %(po)s
			)
		ORDER BY pr.posting_date ASC, pr.name ASC
		""",
		{"po": po_name},
		as_dict=True,
	)


def get_pi_category_account_mismatch(expense):
	"""
	Returns a user-facing error message if the expense's category account does not match
	the account its linked Purchase Invoice booked its cost to, else None.

	The LCV credits only the category's expense account, so a mismatch would strand the
	invoice's debit on the P&L while booking a spurious credit on the category account.
	"""
	if not (expense.payment_type == "Against Purchase Invoice" and expense.purchase_invoice):
		return None

	category_account = frappe.db.get_value("Expense Category", expense.expense_category, "expense_account")
	if not category_account:
		return None

	pi_accounts = list(
		{
			row["expense_account"]
			for row in frappe.db.get_all(
				"Purchase Invoice Item",
				filters={"parent": expense.purchase_invoice, "expense_account": ["is", "set"]},
				fields=["expense_account"],
			)
		}
	)
	if not pi_accounts:
		return None

	if len(pi_accounts) > 1:
		return _(
			f"Purchase Invoice <b>{expense.purchase_invoice}</b> booked its cost to multiple "
			f"expense accounts (<b>{', '.join(sorted(pi_accounts))}</b>). For accompanying expenses "
			f"paid against an invoice, the invoice must book its cost to a single expense account "
			f"matching the category <b>{expense.expense_category}</b> (<b>{category_account}</b>) so "
			f"the Landed Cost Voucher clears it in full."
		)

	if pi_accounts[0] != category_account:
		return _(
			f"Purchase Invoice <b>{expense.purchase_invoice}</b> booked its cost to "
			f"<b>{pi_accounts[0]}</b>, but Expense Category <b>{expense.expense_category}</b> points "
			f"to <b>{category_account}</b>. For accompanying expenses paid against an invoice, the "
			f"category must point to the same account the invoice booked so the Landed Cost Voucher "
			f"clears it in full. Change the category or use Direct Payment."
		)

	return None


@frappe.whitelist()
def make_landed_cost_voucher(expense_name):
	"""
	Creates a Landed Cost Voucher for an accompanying expense.
	Supports both scope types:
		- 'Single Purchase Receipt' → one PR on the LCV
		- 'Inbound Shipment'        → all PRs from the shipment on the LCV
	"""
	expense = frappe.get_doc("Expense", expense_name)

	# --- Guards ---
	if not expense.is_accompanying:
		frappe.throw(_("This expense is not marked as an accompanying expense."))
	if expense.docstatus != 1:
		frappe.throw(_("The expense must be submitted before creating an LCV."))
	if expense.landed_cost_voucher:
		frappe.throw(
			_(f"A Landed Cost Voucher already exists for this expense: <b>{expense.landed_cost_voucher}</b>")
		)

	mismatch = get_pi_category_account_mismatch(expense)
	if mismatch:
		frappe.throw(mismatch)

	scope = expense.expense_scope or "Single Purchase Order"

	# --- Fully-received guards (before building the LCV) ---
	if scope == "Inbound Shipment" and expense.linked_shipment:
		receipt_check = check_shipment_fully_received(expense.linked_shipment)
		if not receipt_check["ready"]:
			frappe.throw(_(receipt_check["message"]))

	if scope == "Single Purchase Order" and expense.linked_purchase_order:
		receipt_check = check_purchase_order_fully_received(expense.linked_purchase_order)
		if not receipt_check["ready"]:
			frappe.throw(_(receipt_check["message"]))

	expense_account = frappe.db.get_value("Expense Category", expense.expense_category, "expense_account")
	if not expense_account:
		frappe.throw(_(f"No GL account configured for Expense Category: <b>{expense.expense_category}</b>."))

	# --- Collect purchase receipts for LCV ---
	if scope == "Single Purchase Order":
		if not expense.linked_purchase_order:
			frappe.throw(_("No linked Purchase Order found on this expense."))
		pr_rows = get_prs_from_po(expense.linked_purchase_order)
		if not pr_rows:
			frappe.throw(
				_(f"Purchase Order <b>{expense.linked_purchase_order}</b> has no linked Purchase Receipts.")
			)

	elif scope == "Single Purchase Receipt":
		if not expense.linked_purchase:
			frappe.throw(_("No linked Purchase Receipt found on this expense."))
		pr_doc = frappe.db.get_value(
			"Purchase Receipt",
			expense.linked_purchase,
			["supplier", "grand_total"],
			as_dict=True,
		)
		if not pr_doc:
			frappe.throw(_(f"Purchase Receipt {expense.linked_purchase} not found."))
		pr_rows = [
			{
				"receipt_document": expense.linked_purchase,
				"supplier": pr_doc.supplier,
				"grand_total": pr_doc.grand_total,
			}
		]

	elif scope == "Inbound Shipment":
		if not expense.linked_shipment:
			frappe.throw(_("No Inbound Shipment linked to this expense."))
		pr_rows = frappe.db.get_all(
			"Inbound Shipment Purchase Receipt",
			filters={"parent": expense.linked_shipment},
			fields=["receipt_document", "supplier", "grand_total"],
			order_by="idx asc",
		)
		if not pr_rows:
			frappe.throw(
				_(f"Inbound Shipment <b>{expense.linked_shipment}</b> has no linked Purchase Receipts.")
			)
	else:
		frappe.throw(_(f"Unknown expense scope: {scope}"))

	# --- Build LCV ---
	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = expense.company

	if scope in ("Inbound Shipment", "Single Purchase Order"):
		# Lock to manual so ERPNext never auto-overrides our weight distribution
		lcv.distribute_charges_based_on = "Distribute Manually"

	for row in pr_rows:
		lcv.append(
			"purchase_receipts",
			{
				"receipt_document_type": "Purchase Receipt",
				"receipt_document": row["receipt_document"],
				"supplier": row["supplier"],
				"grand_total": row["grand_total"],
			},
		)

	lcv.append(
		"taxes",
		{
			"description": expense.expense_category,
			"expense_account": expense_account,
			"amount": expense.amount,
		},
	)

	if scope == "Inbound Shipment" and expense.linked_shipment:
		lcv.custom_linked_shipment = expense.linked_shipment

	if scope == "Single Purchase Order" and expense.linked_purchase_order:
		lcv.custom_linked_purchase_order = expense.linked_purchase_order

	lcv.insert(ignore_permissions=True)
	frappe.db.set_value("Expense", expense_name, "landed_cost_voucher", lcv.name)

	return lcv.name


# ------------------------------------------------------------------ #
# Check clearing — Expense mirrors Payment Entry                       #
# ------------------------------------------------------------------ #


def _is_bank_account(account):
	return frappe.get_cached_value("Account", account, "account_type") == "Bank"


def create_expense_check_clearing_je(expense, destination_account, clearing_date):
	"""Create clearing JE for a Direct-Pay check Expense: Dr clearing / Cr Bank."""
	from nbs_customization.controllers.check_clearing import validate_single_currency

	# Use expense's currencies
	company_currency = frappe.get_cached_value("Company", expense.company, "default_currency")
	if expense.paid_from_account_currency != company_currency:
		frappe.throw(
			_(
				"Cheque clearing is only supported in company currency ({0}) for now. Expense {1} is in a foreign currency."
			).format(company_currency, expense.name)
		)
	validate_destination_account(destination_account, expense.company)
	mop = get_check_mop(expense.mode_of_payment)
	clearing_account = expense.paid_from or mop.get("clearing_account_outward")
	if not clearing_account:
		frappe.throw(_("No clearing account configured for cheque Expense {0}.").format(expense.name))
	amount = expense.amount
	is_bank_entry = bool(expense.reference_no and expense.reference_date)
	je = frappe.get_doc(
		doctype="Journal Entry",
		voucher_type="Bank Entry" if is_bank_entry else "Journal Entry",
		company=expense.company,
		posting_date=clearing_date,
		user_remark=_("Cheque clearing against {0}").format(expense.name),
	)
	if is_bank_entry:
		je.cheque_no = expense.reference_no
		je.cheque_date = expense.reference_date
	# Pay: Dr clearing / Cr destination
	je.append(
		"accounts",
		{
			"account": clearing_account,
			"debit_in_account_currency": amount,
			"reference_type": "Expense",
			"reference_name": expense.name,
			"cost_center": expense.cost_center,
		},
	)
	je.append(
		"accounts",
		{
			"account": destination_account,
			"credit_in_account_currency": amount,
			"reference_type": "Expense",
			"reference_name": expense.name,
			"cost_center": expense.cost_center,
		},
	)
	je.insert(ignore_permissions=True)
	je.submit()
	return je.name


def stamp_expense_check_cleared(expense, je_name, clearing_date, source, destination_account):
	"""Conditional stamp of Expense check flags. Returns rowcount."""
	clearance_date = clearing_date if _is_bank_account(destination_account) else None
	frappe.db.sql(
		"""
		update `tabExpense`
		set is_check = %s,
			check_cleared = 1,
			check_clearing_date = %s,
			check_cleared_source = %s,
			clearing_destination_account = %s,
			clearing_journal_entry = %s,
			clearance_date = %s
		where name = %s and docstatus = 1 and ifnull(check_cleared, 0) = 0
		""",
		(
			expense.is_check or 1,
			clearing_date,
			source,
			destination_account,
			je_name,
			clearance_date,
			expense.name,
		),
	)
	cursor = getattr(frappe.db, "_cursor", None)
	return (cursor.rowcount if cursor else 0) or 0


@frappe.whitelist(methods=["POST"])
def mark_expense_check_cleared(name, destination_account=None, clearing_date=None):
	exp = frappe.get_doc("Expense", name)
	if exp.docstatus != 1:
		frappe.throw(_("Only submitted Expenses can be marked cleared."))
	if not exp.is_check:
		mop = get_check_mop(exp.mode_of_payment)
		if not mop.get("is_check"):
			frappe.throw(_("{0} is not a cheque Expense.").format(exp.name))
	if exp.check_cleared or exp.check_returned:
		frappe.throw(_("{0} is already cleared or returned.").format(exp.name))
	mop = get_check_mop(exp.mode_of_payment)
	chosen = (
		destination_account or exp.clearing_destination_account or mop.get("default_clearing_destination")
	)
	if not chosen:
		chosen = frappe.get_cached_value("Company", exp.company, "default_bank_account")
	clear_date = clearing_date or today()
	# PE path — delegate to PE clearing and mirror
	if exp.payment_entry:
		result = frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_cleared",
			name=exp.payment_entry,
			destination_account=chosen,
			clearing_date=clear_date,
		)
		je_name = result["journal_entry"]
		rows = stamp_expense_check_cleared(exp, je_name, clear_date, "Button", chosen)
		if rows != 1:
			frappe.get_doc("Journal Entry", je_name).cancel()
			frappe.throw(_("{0} was already cleared.").format(exp.name))
		return {"journal_entry": je_name, "cleared": True}
	# Direct JE path
	je_name = create_expense_check_clearing_je(exp, chosen, clear_date)
	rows = stamp_expense_check_cleared(exp, je_name, clear_date, "Button", chosen)
	if rows != 1:
		frappe.get_doc("Journal Entry", je_name).cancel()
		frappe.throw(_("{0} was already cleared.").format(exp.name))
	return {"journal_entry": je_name, "cleared": True}


@frappe.whitelist(methods=["POST"])
def mark_expense_check_returned(name):
	exp = frappe.get_doc("Expense", name)
	if exp.docstatus != 1:
		frappe.throw(_("Only submitted Expenses can be marked returned."))
	if exp.check_returned:
		frappe.throw(_("{0} is already marked returned.").format(exp.name))
	if exp.clearing_journal_entry:
		frappe.db.set_value("Expense", exp.name, "clearing_journal_entry", None, update_modified=False)
		je_name = exp.clearing_journal_entry
		if je_name and frappe.db.exists("Journal Entry", je_name):
			je = frappe.get_doc("Journal Entry", je_name)
			if je.docstatus == 1:
				je.cancel()
	# PE path: return underlying PE (which cancels its clearing JE + itself)
	if exp.payment_entry:
		frappe.call(
			"nbs_customization.controllers.payment_entry.mark_check_returned",
			name=exp.payment_entry,
		)
	# Option A: cancel the Expense itself (like PE)
	exp.cancel()
	frappe.db.set_value(
		"Expense",
		exp.name,
		{
			"check_returned": 1,
			"check_return_date": today(),
			"check_cleared": 0,
			"check_clearing_date": None,
			"check_cleared_source": None,
			"clearing_destination_account": None,
			"clearance_date": None,
		},
	)
	return {"returned": True}
