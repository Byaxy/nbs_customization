# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

"""
Patch: backfill_company_fields
-------------------------------
Backfills the `company` field on three custom doctypes that were created
before multi-company support was added.

Doctypes handled:
  1. Customer Delivery Note  → company from sales_order.company
  2. Promissory Note         → company from sales_order.company
  3. Loan Waybill            → company from source_warehouse.company

Design principles:
  - Idempotent: only touches records where company IS NULL or blank.
    Safe to re-run without risk of overwriting manually corrected data.
  - Bulk SQL via JOIN: no record-by-record Python loops. Fast on large datasets.
  - Orphan detection: after each bulk update, a second query finds any records
    that still have no company (e.g. their linked SO or Warehouse was deleted).
    These are logged to the Error Log for manual review — the patch does NOT
    abort on them, allowing the migration to complete successfully.
  - Commit-safe: frappe.db.commit() is called once at the end. Individual
    section commits are intentionally avoided so a failure rolls back cleanly.

Run position: [post_model_sync] — the `company` column must already exist
in the DB schema before this patch writes to it.
"""

import frappe


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def execute():
     results = {}

     frappe.logger().info("[backfill_company_fields] Starting company field backfill...")

     results["Customer Delivery Note"] = _backfill_cdn()
     results["Promissory Note"]        = _backfill_promissory_note()
     results["Loan Waybill"]           = _backfill_loan_waybill()

     frappe.db.commit()

     _log_summary(results)


# ---------------------------------------------------------------------------
# Per-doctype backfill functions
# ---------------------------------------------------------------------------

def _backfill_cdn():
     """
     Customer Delivery Note.company ← Sales Order.company
     CDN.sales_order is mandatory, so every record should resolve cleanly.
     """
     doctype = "Customer Delivery Note"
     table   = "tabCustomer Delivery Note"

     null_count = _count_null_company(table)
     if not null_count:
          frappe.logger().info(f"[backfill_company_fields] {doctype}: already complete, skipping.")
          return {"updated": 0, "orphaned": 0}

     frappe.logger().info(
          f"[backfill_company_fields] {doctype}: {null_count} records need backfill..."
     )

     frappe.db.sql(f"""
          UPDATE `{table}` cdn
          INNER JOIN `tabSales Order` so
               ON so.name = cdn.sales_order
          SET cdn.company = so.company
          WHERE (cdn.company IS NULL OR cdn.company = '')
          AND cdn.sales_order IS NOT NULL
          AND cdn.sales_order != ''
     """)

     orphans = frappe.db.sql(f"""
          SELECT name, sales_order
          FROM `{table}`
          WHERE company IS NULL OR company = ''
     """, as_dict=True)

     if orphans:
          _log_orphans(doctype, "sales_order", orphans)

     updated = null_count - len(orphans)
     return {"updated": updated, "orphaned": len(orphans)}


def _backfill_promissory_note():
     """
     Promissory Note.company ← Sales Order.company
     PN.sales_order is mandatory, so every record should resolve cleanly.
     """
     doctype = "Promissory Note"
     table   = "tabPromissory Note"

     null_count = _count_null_company(table)
     if not null_count:
          frappe.logger().info(f"[backfill_company_fields] {doctype}: already complete, skipping.")
          return {"updated": 0, "orphaned": 0}

     frappe.logger().info(
          f"[backfill_company_fields] {doctype}: {null_count} records need backfill..."
     )

     frappe.db.sql(f"""
          UPDATE `{table}` pn
          INNER JOIN `tabSales Order` so
               ON so.name = pn.sales_order
          SET pn.company = so.company
          WHERE (pn.company IS NULL OR pn.company = '')
          AND pn.sales_order IS NOT NULL
          AND pn.sales_order != ''
     """)

     orphans = frappe.db.sql(f"""
          SELECT name, sales_order
          FROM `{table}`
          WHERE company IS NULL OR company = ''
     """, as_dict=True)

     if orphans:
          _log_orphans(doctype, "sales_order", orphans)

     updated = null_count - len(orphans)
     return {"updated": updated, "orphaned": len(orphans)}


def _backfill_loan_waybill():
     """
     Loan Waybill.company ← Warehouse.company (via source_warehouse)
     LWB has no Sales Order at creation — company is derived from its
     source warehouse, which is the same pattern ERPNext uses for Stock Entry.
     """
     doctype = "Loan Waybill"
     table   = "tabLoan Waybill"

     null_count = _count_null_company(table)
     if not null_count:
          frappe.logger().info(f"[backfill_company_fields] {doctype}: already complete, skipping.")
          return {"updated": 0, "orphaned": 0}

     frappe.logger().info(
          f"[backfill_company_fields] {doctype}: {null_count} records need backfill..."
     )

     frappe.db.sql(f"""
          UPDATE `{table}` lw
          INNER JOIN `tabWarehouse` wh
               ON wh.name = lw.source_warehouse
          SET lw.company = wh.company
          WHERE (lw.company IS NULL OR lw.company = '')
          AND lw.source_warehouse IS NOT NULL
          AND lw.source_warehouse != ''
     """)

     orphans = frappe.db.sql(f"""
          SELECT name, source_warehouse
          FROM `{table}`
          WHERE company IS NULL OR company = ''
     """, as_dict=True)

     if orphans:
          _log_orphans(doctype, "source_warehouse", orphans)

     updated = null_count - len(orphans)
     return {"updated": updated, "orphaned": len(orphans)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_null_company(table: str) -> int:
     """Returns the count of rows where company is NULL or blank."""
     result = frappe.db.sql(f"""
          SELECT COUNT(*) FROM `{table}`
          WHERE company IS NULL OR company = ''
     """)
     return result[0][0] if result else 0


def _log_orphans(doctype: str, link_field: str, orphans: list):
     """
     Writes a single Error Log entry listing all records that could not
     be backfilled. These need manual review — their linked SO or Warehouse
     may have been deleted from the system.
     """
     lines = [
          f"  {r['name']} ({link_field}: {r.get(link_field) or 'MISSING'})"
          for r in orphans
     ]
     message = (
          f"Could not backfill company for {len(orphans)} {doctype} record(s).\n"
          f"These records have no resolvable {link_field} in the database.\n"
          f"Review and set company manually:\n\n"
          + "\n".join(lines)
     )
     frappe.log_error(message, f"Backfill Company Fields — {doctype} Orphans")
     frappe.logger().warning(
          f"[backfill_company_fields] {doctype}: {len(orphans)} orphan(s) logged to Error Log."
     )


def _log_summary(results: dict):
     """Prints a clean summary table to the bench log."""
     total_updated  = sum(r["updated"]  for r in results.values())
     total_orphaned = sum(r["orphaned"] for r in results.values())

     lines = ["[backfill_company_fields] ── Summary ─────────────────────────"]
     for doctype, r in results.items():
          lines.append(
               f"  {doctype:<30}  updated: {r['updated']:>4}   orphaned: {r['orphaned']:>4}"
          )
     lines.append(f"  {'TOTAL':<30}  updated: {total_updated:>4}   orphaned: {total_orphaned:>4}")
     lines.append("─" * 60)

     if total_orphaned:
          lines.append(
               f"  ⚠  {total_orphaned} record(s) could not be resolved. "
               "Check Error Log for details."
          )
     else:
          lines.append("  ✓  All records resolved successfully.")

     for line in lines:
          frappe.logger().info(line)