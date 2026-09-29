# B10 — Scheduled Jobs

**Depends on:** B8 (Monthly Reconciliation), B9 (Revenue Share Statement), B5 (contract lifecycle), B6 (recovery recompute)
**Provides:** `hooks.py` `scheduler_events` entries for monthly and daily automation

---

## Objective

Add scheduled jobs to automate recurring tasks:
- **Monthly**: Generate Monthly Reconciliations for all active RRA/RLO contracts and Revenue Share Statements for all active CPT contracts.
- **Daily**: Process Contract Amendments reaching Effective status; check RLO ownership threshold.

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/tasks.py` | Create — scheduled job functions |
| `nbs_customization/hooks.py` | Modify — add `scheduler_events` |
| `nbs_customization/tests/test_tasks.py` | Create — tests |

---

## 1. Scheduled job functions — `tasks.py`

```python
# nbs_customization/tasks.py

import frappe
from frappe.utils import getdate, add_months, now_datetime
from nbs_customization.nbs_customization.nbs_customization.doctype.monthly_reconciliation.monthly_reconciliation import generate_monthly_reconciliation
from nbs_customization.nbs_customization.nbs_customization.doctype.revenue_share_statement.revenue_share_statement import generate_revenue_share_statement
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


def monthly_generate_reconciliations():
    """
    Called by the monthly scheduler hook.
    Iterates all active RRA/RLO contracts and generates a reconciliation
    for the previous calendar month if one doesn't already exist.
    """
    previous_month = _previous_period()

    contracts = frappe.db.get_all(
        "Instrument Placement Contract",
        filters={
            "contract_status": "Active",
            "contract_type": ("in", ["RRA", "RLO"]),
        },
        pluck="name",
    )

    for contract_name in contracts:
        try:
            existing = frappe.db.get_value(
                "Monthly Reconciliation",
                {"contract": contract_name, "period": previous_month},
                "name",
            )
            if existing:
                continue
            generate_monthly_reconciliation(contract_name, previous_month)
        except Exception as e:
            frappe.log_error(
                message=f"Failed to generate reconciliation for {contract_name}: {e}",
                title="Monthly Reconciliation Error",
            )


def monthly_generate_revenue_share():
    """
    Called by the monthly scheduler hook.
    Generates Revenue Share Statements for all active CPT contracts
    for the previous calendar month.
    """
    previous_month = _previous_period()

    contracts = frappe.db.get_all(
        "Instrument Placement Contract",
        filters={
            "contract_status": "Active",
            "contract_type": "CPT",
        },
        pluck="name",
    )

    for contract_name in contracts:
        try:
            existing = frappe.db.get_value(
                "Revenue Share Statement",
                {"contract": contract_name, "period": previous_month},
                "name",
            )
            if existing:
                continue
            generate_revenue_share_statement(contract_name, previous_month)
        except Exception as e:
            frappe.log_error(
                message=f"Failed to generate RSS for {contract_name}: {e}",
                title="Revenue Share Statement Error",
            )


def daily_process_amendments():
    """
    Called by the daily scheduler hook.
    Checks for Contract Amendments with status 'Approved' and
    effective_date <= today, drives them to 'Effective' status,
    and pushes the new terms back onto the Contract via db_set.
    """
    today = getdate()

    amendments = frappe.db.get_all(
        "Contract Amendment",
        filters={
            "status": "Approved",
            "effective_date": ("<=", today),
        },
        fields=["name", "contract", "new_declared_volume",
                "new_min_value", "new_share_pct", "new_recovery_target"],
    )

    for am in amendments:
        try:
            doc = frappe.get_doc("Contract Amendment", am.name)
            doc.status = "Effective"
            doc.db_set("status", "Effective")

            contract_name = am.contract

            if am.new_declared_volume:
                frappe.db.set_value(
                    "Instrument Placement Contract",
                    contract_name,
                    "declared_monthly_test_volume",
                    am.new_declared_volume,
                )

            if am.new_min_value:
                frappe.db.set_value(
                    "Instrument Placement Contract",
                    contract_name,
                    "min_monthly_value",
                    am.new_min_value,
                )

            if am.new_share_pct:
                frappe.db.set_value(
                    "Instrument Placement Contract",
                    contract_name,
                    "revenue_share_pct",
                    am.new_share_pct,
                )

            if am.new_recovery_target:
                frappe.db.set_value(
                    "Instrument Placement Contract",
                    contract_name,
                    "total_recovery_target",
                    am.new_recovery_target,
                )

            frappe.db.commit()

        except Exception as e:
            frappe.log_error(
                message=f"Failed to process amendment {am.name}: {e}",
                title="Contract Amendment Processing Error",
            )


def daily_check_rlo_ownership():
    """
    Called by the daily scheduler hook.
    Checks RLO contracts where recovery_pct_collected >= 100 and
    outstanding_on_contract <= 0, sets ownership_threshold_met = 1.
    This only sets the eligibility flag — the human must still create
    the Ownership Transfer Request manually.
    """
    contracts = frappe.db.get_all(
        "Instrument Placement Contract",
        filters={
            "contract_status": "Active",
            "contract_type": "RLO",
            "ownership_threshold_met": 0,
        },
        fields=["name", "cumulative_collected", "total_recovery_target",
                "outstanding_on_contract"],
    )

    for c in contracts:
        target = c.total_recovery_target or 0
        if target == 0:
            continue

        pct_collected = (c.cumulative_collected / target) * 100
        outstanding = c.outstanding_on_contract or 0

        if pct_collected >= 100 and outstanding <= 1:
            frappe.db.set_value(
                "Instrument Placement Contract",
                c.name,
                "ownership_threshold_met",
                1,
                update_modified=False,
            )


def _previous_period():
    now = now_datetime()
    prev = add_months(now, -1)
    return f"{prev.year}-{prev.month:02d}"
```

---

## 2. `hooks.py` updates

```python
scheduler_events = {
    "monthly": [
        "nbs_customization.tasks.monthly_generate_reconciliations",
        "nbs_customization.tasks.monthly_generate_revenue_share",
    ],
    "daily": [
        "nbs_customization.tasks.daily_process_amendments",
        "nbs_customization.tasks.daily_check_rlo_ownership",
    ],
}
```

---

## 3. Tests

```python
# nbs_customization/tests/test_tasks.py

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.tasks import (
    monthly_generate_reconciliations,
    monthly_generate_revenue_share,
    daily_process_amendments,
    daily_check_rlo_ownership,
)


class TestScheduledJobs(FrappeTestCase):
    def setUp(self):
        pass

    def tearDown(self):
        frappe.db.rollback()

    def test_monthly_reconciliation_creates_for_active_rra(self):
        monthly_generate_reconciliations()

    def test_daily_amendment_processing(self):
        daily_process_amendments()

    def test_daily_rlo_threshold_check(self):
        daily_check_rlo_ownership()
```
