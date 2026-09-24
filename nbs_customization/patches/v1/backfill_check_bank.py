# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""
Patch: backfill_check_bank
---------------------------
Fills check_bank (Link:Bank) for historic check documents where
is_check==1 but check_bank is blank.

Pay vs Receive split (strict Receive fallback per decisions a/b/c):
  Pay:   1) clearing_journal_entry -> Journal Entry Account (Bank/Cash) -> Bank Account.bank
         2) clearing_destination_account -> Bank Account -> Bank
         3) paid_from where account_type=Bank -> Bank Account -> Bank
         4) Mode of Payment.default_clearing_destination -> Bank Account -> Bank
         5) Company.default_bank_account -> Bank Account -> Bank
  Receive: never use clearing_destination_account (our bank ≠ drawer bank).
         1) clearing_journal_entry -> JE Bank/Cash trace (cash like Petty Cash -> None)
         2) Bank Transaction.reference_number (= PE.reference_no) -> Bank Account -> Bank
         3) Receipt reverse-lookup: Receipt Payment -> Receipt Payment Method bank
         If none, leave NULL and log to Error Log (decision a: no bank_name -> manual).
         Cash-cleared Receive to Petty Cash - USD - NBS has no Bank Account -> NULL (decision c).

Also backfills:
  - Receipt Payment.check_bank from linked Payment Entry.check_bank
  - Receipt Payment Method.check_bank from hidden bank_name where Bank exists,
    or from grouped Receipt Payments, plus single-distinct-child pass.

Idempotent: all UPDATEs guarded WHERE check_bank IS NULL OR ''.
Run position: [post_model_sync] — check_bank column must already exist.
"""

import frappe

# Cheque transit accounts — never the destination bank.
_TRANSIT_ACCOUNTS = (
	"Cheques in Transit - Inward - NBS",
	"Cheques in Transit - Outward - NBS",
)


def execute():
	results = {}
	frappe.logger().info("[backfill_check_bank] Starting check_bank backfill...")

	results["Payment Entry"] = _backfill_payment_entry()
	results["Expense"] = _backfill_expense()
	results["Commission Payout"] = _backfill_commission()
	results["Receipt Payment"] = _backfill_receipt_payment()
	results["Receipt Payment Method"] = _backfill_receipt_method()

	frappe.db.commit()
	_log_summary(results)


def _resolve_bank_from_account(account):
	if not account:
		return None
	return frappe.db.get_value("Bank Account", {"account": account}, "bank")


def _get_je_destination_bank(clearing_journal_entry):
	"""Most authoritative: JE destination Bank/Cash account -> Bank.

	Returns Bank name or None. For Cash accounts with no Bank Account row
	(e.g. Petty Cash - USD - NBS) returns None per decision (c).
	"""
	if not clearing_journal_entry:
		return None
	rows = frappe.db.sql(
		"""
		SELECT jea.account
		FROM `tabJournal Entry Account` jea
		JOIN `tabAccount` acc ON acc.name = jea.account
		WHERE jea.parent = %s
		  AND acc.account_type IN ('Bank', 'Cash')
		  AND jea.account NOT IN %s
		""",
		(clearing_journal_entry, _TRANSIT_ACCOUNTS),
		as_dict=True,
	)
	for r in rows:
		bank = _resolve_bank_from_account(r.account)
		if bank:
			return bank
		# Cash with no Bank Account (Petty Cash) -> explicit None, don't fall through to ECOBANK default
		acc_type = frappe.db.get_value("Account", r.account, "account_type")
		if acc_type == "Cash":
			return None
	return None


def _get_bank_transaction_bank(reference_no):
	if not reference_no:
		return None
	row = frappe.db.sql(
		"""
		SELECT ba.bank
		FROM `tabBank Transaction` bt
		JOIN `tabBank Account` ba ON ba.name = bt.bank_account
		WHERE bt.reference_number = %s
		LIMIT 1
		""",
		(reference_no,),
		as_dict=True,
	)
	if row and row[0].get("bank"):
		return row[0].bank
	return None


def _get_receipt_bank(pe_name):
	"""Reverse-lookup Receipt Payment Method via Receipt Payment -> Receipt.

	Prefers already-resolved check_bank, else hidden bank_name where Bank exists.
	"""
	if not pe_name:
		return None
	# via Receipt Payment -> Receipt -> Receipt Payment Method
	rows = frappe.db.sql(
		"""
		SELECT bpm.check_bank AS cb, bpm.bank_name AS bn
		FROM `tabReceipt Payment` rp
		JOIN `tabReceipt` r ON r.name = rp.parent
		JOIN `tabReceipt Payment Method` bpm ON bpm.parent = r.name
		WHERE rp.payment_entry = %s
		  AND (bpm.check_bank IS NOT NULL AND bpm.check_bank != ''
		       OR bpm.bank_name IS NOT NULL AND bpm.bank_name != '')
		LIMIT 1
		""",
		(pe_name,),
		as_dict=True,
	)
	if not rows:
		# fallback: direct Receipt Payment row may have been backfilled already
		return None
	r = rows[0]
	if r.get("cb") and frappe.db.exists("Bank", r.cb):
		return r.cb
	if r.get("bn") and frappe.db.exists("Bank", r.bn):
		return r.bn
	return None


def _resolve_pe_check_bank(row):
	"""Strict Pay/Receive resolver. row has payment_type, clearing fields, etc."""
	is_pay = row.get("payment_type") == "Pay"

	if is_pay:
		b = _get_je_destination_bank(row.get("clearing_journal_entry"))
		if b:
			return b
		b = _resolve_bank_from_account(row.get("clearing_destination_account"))
		if b:
			return b
		paid_from = row.get("paid_from")
		if paid_from:
			try:
				acc_type = frappe.get_cached_value("Account", paid_from, "account_type")
			except Exception:
				acc_type = frappe.db.get_value("Account", paid_from, "account_type")
			if acc_type == "Bank":
				b = _resolve_bank_from_account(paid_from)
				if b:
					return b
	else:
		# Receive — never use clearing_destination_account or JE destination
		# (both are our bank, not drawer bank). Only Bank Transaction / Receipt.
		if row.get("reference_no"):
			b = _get_bank_transaction_bank(row.get("reference_no"))
			if b:
				return b
			b = _get_receipt_bank(row.get("name"))
			if b:
				return b
		else:
			# decision (a): no reference_no -> try receipt anyway, else leave NULL
			b = _get_receipt_bank(row.get("name"))
			if b:
				return b
		# decision (c): cash-cleared Receive (e.g. Petty Cash JE) also stays NULL
		# since Petty Cash has no Bank Account row.
		return None

	# Pay fallbacks only
	if row.get("mode_of_payment"):
		mop = frappe.db.get_value("Mode of Payment", row.get("mode_of_payment"), "default_clearing_destination")
		b = _resolve_bank_from_account(mop)
		if b:
			return b
	if row.get("company"):
		company_bank = frappe.db.get_value("Company", row.get("company"), "default_bank_account")
		b = _resolve_bank_from_account(company_bank)
		if b:
			return b
	return None


def _backfill_payment_entry():
	table = "tabPayment Entry"
	if not _has_column(table, "check_bank"):
		frappe.logger().info("[backfill_check_bank] Payment Entry: no check_bank column yet, skipping.")
		return {"updated": 0, "unmatched": 0}

	rows = frappe.db.sql(
		f"""
		SELECT name, company, mode_of_payment, payment_type,
		       clearing_destination_account, clearing_journal_entry, paid_from, paid_to, reference_no
		FROM `{table}`
		WHERE (check_bank IS NULL OR check_bank='')
		  AND (ifnull(is_check,0)=1 OR mode_of_payment IN (SELECT name FROM `tabMode of Payment` WHERE is_check=1))
		""",
		as_dict=True,
	)
	if not rows:
		return {"updated": 0, "unmatched": 0}

	updated = 0
	unmatched = []
	receive_unmatched = []
	pay_unmatched = []

	for r in rows:
		bank = _resolve_pe_check_bank(r)
		if bank:
			frappe.db.sql(
				f"UPDATE `{table}` SET check_bank=%s WHERE name=%s AND (check_bank IS NULL OR check_bank='')",
				(bank, r.name),
			)
			updated += 1
		else:
			unmatched.append(r.name)
			if r.get("payment_type") == "Receive":
				receive_unmatched.append(r.name)
			else:
				pay_unmatched.append(r.name)

	if receive_unmatched:
		_log_unmatched("Payment Entry Receive-needs-manual", receive_unmatched)
	if pay_unmatched:
		_log_unmatched("Payment Entry Pay-unmatched", pay_unmatched)
	elif unmatched and not receive_unmatched and not pay_unmatched:
		_log_unmatched("Payment Entry", unmatched)

	return {"updated": updated, "unmatched": len(unmatched)}


def _backfill_expense():
	table = "tabExpense"
	if not _has_column(table, "check_bank"):
		return {"updated": 0, "unmatched": 0}

	rows = frappe.db.sql(
		f"""
		SELECT name, company, mode_of_payment, clearing_destination_account, clearing_journal_entry, reference_no
		FROM `{table}`
		WHERE (check_bank IS NULL OR check_bank='')
		  AND (ifnull(is_check,0)=1 OR mode_of_payment IN (SELECT name FROM `tabMode of Payment` WHERE is_check=1))
		""",
		as_dict=True,
	)
	if not rows:
		return {"updated": 0, "unmatched": 0}

	updated = 0
	unmatched = []
	for r in rows:
		bank = None
		b = _get_je_destination_bank(r.get("clearing_journal_entry"))
		if b:
			bank = b
		else:
			# Expense is Pay-like: clearing dest is our bank (= drawer for outgoing)
			bank = _resolve_pe_check_bank(
				{
					"name": r.name,
					"payment_type": "Pay",
					"company": r.get("company"),
					"mode_of_payment": r.get("mode_of_payment"),
					"clearing_destination_account": r.get("clearing_destination_account"),
					"clearing_journal_entry": r.get("clearing_journal_entry"),
					"paid_from": None,
					"paid_to": None,
					"reference_no": r.get("reference_no"),
				}
			)
		if bank:
			frappe.db.sql(
				f"UPDATE `{table}` SET check_bank=%s WHERE name=%s AND (check_bank IS NULL OR check_bank='')",
				(bank, r.name),
			)
			updated += 1
		else:
			unmatched.append(r.name)

	if unmatched:
		_log_unmatched("Expense", unmatched)
	return {"updated": updated, "unmatched": len(unmatched)}


def _backfill_commission():
	table = "tabCommission Payout"
	if not _has_column(table, "check_bank"):
		return {"updated": 0, "unmatched": 0}

	rows = frappe.db.sql(
		f"""
		SELECT name, company, mode_of_payment, clearing_destination_account, clearing_journal_entry, reference_no
		FROM `{table}`
		WHERE (check_bank IS NULL OR check_bank='')
		  AND (ifnull(is_check,0)=1 OR mode_of_payment IN (SELECT name FROM `tabMode of Payment` WHERE is_check=1))
		""",
		as_dict=True,
	)
	if not rows:
		return {"updated": 0, "unmatched": 0}

	updated = 0
	unmatched = []
	for r in rows:
		b = _get_je_destination_bank(r.get("clearing_journal_entry"))
		bank = b
		if not bank:
			bank = _resolve_pe_check_bank(
				{
					"name": r.name,
					"payment_type": "Pay",
					"company": r.get("company"),
					"mode_of_payment": r.get("mode_of_payment"),
					"clearing_destination_account": r.get("clearing_destination_account"),
					"clearing_journal_entry": r.get("clearing_journal_entry"),
					"paid_from": None,
					"paid_to": None,
					"reference_no": r.get("reference_no"),
				}
			)
		if bank:
			frappe.db.sql(
				f"UPDATE `{table}` SET check_bank=%s WHERE name=%s AND (check_bank IS NULL OR check_bank='')",
				(bank, r.name),
			)
			updated += 1
		else:
			unmatched.append(r.name)

	if unmatched:
		_log_unmatched("Commission Payout", unmatched)
	return {"updated": updated, "unmatched": len(unmatched)}


def _backfill_receipt_payment():
	table = "tabReceipt Payment"
	if not _has_column(table, "check_bank"):
		return {"updated": 0, "unmatched": 0}
	if not _has_column("tabPayment Entry", "check_bank"):
		return {"updated": 0, "unmatched": 0}

	# Direct join update from PE (idempotent guard on rp side)
	frappe.db.sql(
		f"""
		UPDATE `{table}` rp
		INNER JOIN `tabPayment Entry` pe ON pe.name = rp.payment_entry
		SET rp.check_bank = pe.check_bank
		WHERE (rp.check_bank IS NULL OR rp.check_bank='')
		AND pe.check_bank IS NOT NULL AND pe.check_bank != ''
		"""
	)
	cnt = frappe.db.sql(f"SELECT COUNT(*) FROM `{table}` WHERE check_bank IS NOT NULL AND check_bank!=''")[0][
		0
	]
	return {"updated": cnt, "unmatched": 0}


def _backfill_receipt_method():
	table = "tabReceipt Payment Method"
	if not _has_column(table, "check_bank"):
		return {"updated": 0, "unmatched": 0}

	# 1. Map hidden bank_name -> check_bank where Bank exists
	rows = frappe.db.sql(
		f"""
		SELECT name, bank_name
		FROM `{table}`
		WHERE (check_bank IS NULL OR check_bank='')
		AND bank_name IS NOT NULL AND bank_name != ''
		""",
		as_dict=True,
	)
	updated = 0
	for r in rows:
		if frappe.db.exists("Bank", r.bank_name):
			frappe.db.sql(
				f"UPDATE `{table}` SET check_bank=%s WHERE name=%s AND (check_bank IS NULL OR check_bank='')",
				(r.bank_name, r.name),
			)
			updated += 1

	# 2. For remaining, infer from parent Receipt Payments grouped by method+ref
	remaining = frappe.db.sql(
		f"""
		SELECT name, parent, payment_method, reference_no
		FROM `{table}`
		WHERE (check_bank IS NULL OR check_bank='')
		""",
		as_dict=True,
	)
	for rm in remaining:
		bank = frappe.db.sql(
			"""
			SELECT rp.check_bank FROM `tabReceipt Payment` rp
			WHERE rp.parent=%s AND rp.payment_method=%s AND ifnull(rp.reference_no,'')=ifnull(%s,'')
			AND rp.check_bank IS NOT NULL AND rp.check_bank!=''
			LIMIT 1
			""",
			(rm.parent, rm.payment_method, rm.reference_no or ""),
		)
		if bank and bank[0][0]:
			frappe.db.sql(
				f"UPDATE `{table}` SET check_bank=%s WHERE name=%s AND (check_bank IS NULL OR check_bank='')",
				(bank[0][0], rm.name),
			)
			updated += 1

	# 3. Single distinct child pass: if all Receipt Payments under same parent/method share one check_bank, copy it
	still_remaining = frappe.db.sql(
		f"""
		SELECT name, parent, payment_method
		FROM `{table}`
		WHERE (check_bank IS NULL OR check_bank='')
		""",
		as_dict=True,
	)
	for rm in still_remaining:
		distinct = frappe.db.sql(
			"""
			SELECT COUNT(DISTINCT rp.check_bank), MAX(rp.check_bank)
			FROM `tabReceipt Payment` rp
			WHERE rp.parent=%s AND rp.payment_method=%s
			  AND rp.check_bank IS NOT NULL AND rp.check_bank!=''
			""",
			(rm.parent, rm.payment_method),
		)
		if distinct and distinct[0][0] == 1 and distinct[0][1]:
			if frappe.db.exists("Bank", distinct[0][1]):
				frappe.db.sql(
					f"UPDATE `{table}` SET check_bank=%s WHERE name=%s AND (check_bank IS NULL OR check_bank='')",
					(distinct[0][1], rm.name),
				)
				updated += 1

	if updated == 0:
		return {"updated": 0, "unmatched": 0}
	return {"updated": updated, "unmatched": 0}


def _has_column(table, column):
	try:
		return frappe.db.has_column(table, column)
	except Exception:
		res = frappe.db.sql(
			"SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
			(table, column),
		)
		return bool(res)


def _log_unmatched(doctype, names):
	msg = (
		f"Could not resolve check_bank for {len(names)} {doctype} record(s) with is_check=1.\n"
		f"No Bank mapping found (Pay: JE/clearing/MOP/company; Receive: JE/Bank Transaction/Receipt).\n"
		f"Review and set Check Bank manually:\n\n" + "\n".join(f"  {n}" for n in names)
	)
	try:
		frappe.log_error(msg, f"Backfill Check Bank — {doctype} Unmatched")
	except Exception:
		pass
	frappe.logger().warning(f"[backfill_check_bank] {doctype}: {len(names)} unmatched logged to Error Log.")


def _log_summary(results):
	lines = ["[backfill_check_bank] ── Summary ─────────────────────────"]
	total_updated = 0
	total_unmatched = 0
	for dt, r in results.items():
		lines.append(f"  {dt:<25}  updated: {r['updated']:>4}   unmatched: {r['unmatched']:>4}")
		total_updated += r["updated"]
		total_unmatched += r["unmatched"]
	lines.append(f"  {'TOTAL':<25}  updated: {total_updated:>4}   unmatched: {total_unmatched:>4}")
	lines.append("─" * 60)
	if total_unmatched:
		lines.append(f"  ⚠  {total_unmatched} record(s) could not be resolved. Check Error Log.")
	else:
		lines.append("  ✓  All resolvable records backfilled.")
	for line in lines:
		frappe.logger().info(line)
