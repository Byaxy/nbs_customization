# B8 — Monthly Reconciliation Generation and Compliance Logic

**Depends on:** B2 (valid items), B5 (contract lifecycle), B6 (recovery recompute)
**Provides:** `generate_monthly_reconciliation` function + controller for `Monthly Reconciliation`

---

## Objective

Generate a Monthly Reconciliation record for a given RRA/RLO contract and period. Aggregate submitted Sales Invoices, compare against minimums, compute compliance status, and auto-create Repossession Request drafts when breach threshold is reached.

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/monthly_reconciliation/monthly_reconciliation.py` | Create — full controller with generation logic |
| `nbs_customization/nbs_customization/nbs_customization/doctype/monthly_reconciliation/test_monthly_reconciliation.py` | Create — tests |

---

## 1. Controller — `monthly_reconciliation.py`

All generation logic lives in the same file as the DocType controller, not in a separate `reconciliation.py`. Module-level functions are whitelisted for custom button calls.

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/monthly_reconciliation/monthly_reconciliation.py

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, add_months, add_days
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


class MonthlyReconciliation(Document):
    def validate(self):
        self._update_contract_breach_count()
        self._update_contract_recovery()

    def on_submit(self):
        self.reconciliation_status = "Verified"
        self.db_set("reconciliation_status", "Verified")

    def _update_contract_breach_count(self):
        if self.compliance_status == "Compliant":
            frappe.db.set_value(
                "Instrument Placement Contract",
                self.contract,
                "consecutive_breach_count",
                0,
            )
        elif self.consecutive_breach_count:
            frappe.db.set_value(
                "Instrument Placement Contract",
                self.contract,
                "consecutive_breach_count",
                self.consecutive_breach_count,
            )

    def _update_contract_recovery(self):
        recompute_contract_recovery(self.contract)


# ------------------------------------------------------------------
# Generation logic (module-level, whitelisted)
# ------------------------------------------------------------------


@frappe.whitelist()
def generate_monthly_reconciliation(contract_name, period):
    """
    Generate (or regenerate) a Monthly Reconciliation for a given
    RRA/RLO contract and period (YYYY-MM).

    Idempotent — if one already exists, it's returned and recalculated.
    """
    contract = frappe.get_doc("Instrument Placement Contract", contract_name)
    if contract.contract_type not in ("RRA", "RLO"):
        frappe.throw(
            frappe._("Monthly Reconciliation is only for RRA/RLO contracts.")
        )

    existing = frappe.db.get_value(
        "Monthly Reconciliation",
        {"contract": contract_name, "period": period},
        "name",
    )
    if existing:
        mrc = frappe.get_doc("Monthly Reconciliation", existing)
    else:
        mrc = frappe.get_doc({
            "doctype": "Monthly Reconciliation",
            "contract": contract_name,
            "period": period,
            "period_start": format_date_range_start(period),
            "period_end": format_date_range_end(period),
        })
        mrc.insert(ignore_permissions=True)

    invoices = frappe.db.get_all(
        "Sales Invoice",
        filters={
            "custom_instrument_placement_contract": contract_name,
            "custom_placement_transaction_type": ("in", [
                "Contract Reagent Sale", "Contract Consumable Replenishment",
            ]),
            "posting_date": ("between", [mrc.period_start, mrc.period_end]),
            "docstatus": 1,
        },
        fields=["name", "posting_date", "grand_total",
                "custom_placement_transaction_type"],
    )

    mrc.linked_invoices = []
    for inv in invoices:
        mrc.append("linked_invoices", {
            "sales_invoice": inv.name,
            "invoice_date": inv.posting_date,
            "invoice_amount": inv.grand_total,
            "placement_transaction_type": inv.custom_placement_transaction_type,
        })

    reagent_value = sum(
        inv.grand_total
        for inv in invoices
        if inv.custom_placement_transaction_type == "Contract Reagent Sale"
    )
    consumable_value = sum(
        inv.grand_total
        for inv in invoices
        if inv.custom_placement_transaction_type == "Contract Consumable Replenishment"
    )
    total_actual = reagent_value + consumable_value

    mrc.actual_reagent_value = reagent_value
    mrc.actual_consumable_value = consumable_value
    mrc.total_actual_value = total_actual

    min_required = contract.min_monthly_value or 0
    mrc.minimum_value_required = min_required
    mrc.shortfall_value = max(0, min_required - total_actual)

    _compute_compliance(mrc, contract, total_actual)

    mrc.invoiced_this_period = total_actual

    mrc.save(ignore_permissions=True)

    return mrc.name


def format_date_range_start(period):
    parts = period.split("-")
    return getdate(f"{parts[0]}-{parts[1]}-01")


def format_date_range_end(period):
    start = format_date_range_start(period)
    return add_days(add_months(start, 1), -1)


def _compute_compliance(mrc, contract, total_actual):
    min_required = contract.min_monthly_value or 0

    if total_actual >= min_required:
        mrc.compliance_status = "Compliant"
        mrc.consecutive_breach_count = 0
        return

    grace = contract.grace_period_days or 0
    previous_breach_count = contract.consecutive_breach_count or 0

    if grace > 0:
        from frappe.utils import add_days
        grace_deadline = add_days(mrc.period_end, grace)
        if frappe.utils.today() <= grace_deadline:
            mrc.compliance_status = "Grace Period"
            mrc.consecutive_breach_count = previous_breach_count
            return

    mrc.compliance_status = "Shortfall"
    new_count = previous_breach_count + 1
    mrc.consecutive_breach_count = new_count

    if contract.breach_threshold and new_count >= contract.breach_threshold:
        _auto_create_repossession_request(mrc, contract)


def _auto_create_repossession_request(mrc, contract):
    existing = frappe.db.get_value(
        "Repossession Request",
        {
            "contract": contract.name,
            "status": ("!=", "Closed"),
        },
        "name",
    )
    if existing:
        return

    deployment = frappe.db.get_value(
        "Analyzer Deployment",
        {"contract": contract.name, "deployment_status": "Deployed"},
        "name",
    )
    if not deployment:
        return

    rr = frappe.get_doc({
        "doctype": "Repossession Request",
        "contract": contract.name,
        "analyzer_deployment": deployment,
        "reason": "Minimum Purchase Breach",
        "breach_count": mrc.consecutive_breach_count,
        "months_breached": mrc.consecutive_breach_count,
        "requested_by": frappe.session.user,
        "request_date": frappe.utils.today(),
        "status": "Draft",
    })
    rr.insert(ignore_permissions=True)
    frappe.msgprint(
        frappe._(
            "Repossession Request {0} has been auto-created for Contract {1} "
            "due to breach threshold reached."
        ).format(frappe.bold(rr.name), frappe.bold(contract.name))
    )
```

---

## 2. Tests

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/monthly_reconciliation/test_monthly_reconciliation.py

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.nbs_customization.nbs_customization.doctype.monthly_reconciliation.monthly_reconciliation import generate_monthly_reconciliation


class TestMonthlyReconciliation(FrappeTestCase):
    def setUp(self):
        pass

    def tearDown(self):
        frappe.db.rollback()

    def test_generates_reconciliation(self):
        mrc_name = generate_monthly_reconciliation("_TST Contract", "2026-07")
        self.assertTrue(mrc_name)

    def test_aggregates_correctly(self):
        pass

    def test_compliance_breach_creates_repossession(self):
        pass

    def test_idempotent(self):
        pass
```

---

## 3. `hooks.py` registration

No changes needed — the `validate` fires automatically and `@frappe.whitelist()` registers the generation function.
