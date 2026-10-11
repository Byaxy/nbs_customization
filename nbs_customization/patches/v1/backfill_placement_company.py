# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""
Patch: backfill_placement_company
----------------------------------
Backfills the `company` field on placement doctypes that were created
before the field existed. Both resolve to the site default company
(single-company site, no source link to derive from).

Doctypes handled:
  1. Instrument Pricing Worksheet  → Global Defaults.default_company
  2. Instrument Placement Contract → Global Defaults.default_company
     (preferred source is the linked worksheet, but legacy rows predate
     the field on both sides, so the default applies throughout)

Design principles (mirrors backfill_company_fields):
  - Idempotent: only touches records where company IS NULL or blank.
  - Bulk SQL: no record-by-record loops.
  - Unresolvable rows (no default company set) are logged to the Error Log;
    the patch does NOT abort, allowing the migration to complete.

Run position: [post_model_sync] — the `company` columns must already exist.
"""

import frappe


def execute():
	default_company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not default_company:
		frappe.log_error(
			"No default Company set in Global Defaults; placement company backfill skipped.",
			"Backfill Placement Company",
		)
		frappe.logger().warning("[backfill_placement_company] No default company, skipping.")
		return

	results = {}
	frappe.logger().info("[backfill_placement_company] Starting company field backfill...")

	results["Instrument Pricing Worksheet"] = _backfill(
		"Instrument Pricing Worksheet", "tabInstrument Pricing Worksheet", default_company
	)
	results["Instrument Placement Contract"] = _backfill(
		"Instrument Placement Contract", "tabInstrument Placement Contract", default_company
	)

	frappe.db.commit()

	_log_summary(results)


def _backfill(doctype: str, table: str, default_company: str) -> dict:
	null_count = frappe.db.sql(
		f"""
		SELECT COUNT(*) FROM `{table}`
		WHERE company IS NULL OR company = ''
		"""
	)[0][0]
	if not null_count:
		frappe.logger().info(f"[backfill_placement_company] {doctype}: already complete, skipping.")
		return {"updated": 0, "orphaned": 0}

	frappe.db.sql(
		f"""
		UPDATE `{table}`
		SET company = %s
		WHERE company IS NULL OR company = ''
		""",
		default_company,
	)

	orphans = frappe.db.sql(
		f"""
		SELECT name FROM `{table}`
		WHERE company IS NULL OR company = ''
		""",
		as_dict=True,
	)
	if orphans:
		lines = [f"  {r['name']}" for r in orphans]
		frappe.log_error(
			f"Could not backfill company for {len(orphans)} {doctype} record(s).\n"
			"Review and set company manually:\n\n" + "\n".join(lines),
			f"Backfill Placement Company — {doctype} Orphans",
		)

	updated = null_count - len(orphans)
	return {"updated": updated, "orphaned": len(orphans)}


def _log_summary(results: dict):
	total_updated = sum(r["updated"] for r in results.values())
	total_orphaned = sum(r["orphaned"] for r in results.values())

	lines = ["[backfill_placement_company] ── Summary ─────────────────────────"]
	for doctype, r in results.items():
		lines.append(f"  {doctype:<30}  updated: {r['updated']:>4}   orphaned: {r['orphaned']:>4}")
	lines.append(f"  {'TOTAL':<30}  updated: {total_updated:>4}   orphaned: {total_orphaned:>4}")
	lines.append("─" * 60)

	if total_orphaned:
		lines.append(f"  ⚠  {total_orphaned} record(s) could not be resolved. Check Error Log for details.")
	else:
		lines.append("  ✓  All records resolved successfully.")

	for line in lines:
		frappe.logger().info(line)
