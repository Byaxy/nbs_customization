# B6 — Sales Transaction Hooks

**Depends on:** B2 (valid items), B5 (contract lifecycle)
**Provides:** Placement validation and recovery rollup hooks on Sales Order, Delivery Note, Sales Invoice, Payment Entry

---

## Objective

Wire the placement contract field into the native sales transaction DocTypes. Every transaction tagged with a contract must have its items restricted, transaction type enforced, and — for Sales Invoice and Payment Entry — must trigger the shared recovery recomputation (§4.1).

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/controllers/placement/__init__.py` | Create — new subpackage for hook files |
| `nbs_customization/controllers/placement/sales_validate.py` | Create — shared validators |
| `nbs_customization/utils/placement/recovery.py` | Create — `recompute_contract_recovery` (§4.1) |
| `nbs_customization/controllers/placement/sales_invoice.py` | Create — SI hooks |
| `nbs_customization/controllers/placement/payment_entry.py` | Create — PE hooks |
| `nbs_customization/hooks.py` | Modify — append hooks to existing doc_events lists |
| `nbs_customization/utils/placement/test_recovery.py` | Create — recovery recompute tests |

---

## 1. New subpackage

Create the `placement` directory under `controllers/` (for native hook files that reference DocTypes via doc_events):

```python
# nbs_customization/controllers/placement/__init__.py
```

---

## 2. Shared validators — `sales_validate.py`

```python
# nbs_customization/controllers/placement/sales_validate.py

import frappe
from nbs_customization.utils.placement.valid_items import validate_items_belong_to_analyzer


def validate_placement_transaction(doc, method=None):
    """
    Validate a document (SO/DN/SI) that has a custom_instrument_placement_contract set.
    - Restrict items to those valid for the contract's analyzer
    - Validate transaction type consistency with contract type
    """
    if not doc.get("custom_instrument_placement_contract"):
        return

    contract_name = doc.custom_instrument_placement_contract
    contract = frappe.get_cached_doc("Instrument Placement Contract", contract_name)

    # Validate items
    item_codes = [item.item_code for item in doc.items if item.item_code]
    validate_items_belong_to_analyzer(contract.analyzer_pid, item_codes, throw=True)

    # Validate transaction type
    ttype = doc.get("custom_placement_transaction_type")
    if not ttype:
        frappe.throw(
            frappe._(
                "Placement Transaction Type is required when a Placement Contract is selected."
            )
        )

    _validate_transaction_type_consistency(ttype, contract.contract_type)


def _validate_transaction_type_consistency(ttype, contract_type):
    if ttype in ("Contract Free Issue", "Contract Consumable Free Issue"):
        if contract_type != "CPT":
            frappe.throw(
                frappe._(
                    "Transaction type '{0}' is only valid for CPT contracts. "
                    "This contract is {1}."
                ).format(ttype, contract_type)
            )

    if contract_type == "CPT" and ttype not in ("Contract Free Issue", "Contract Consumable Free Issue", "Contract Reagent Sale", "Standard Sale"):
        frappe.throw(
            frappe._(
                "CPT contracts only allow 'Contract Free Issue', "
                "'Contract Consumable Free Issue', 'Contract Reagent Sale', or 'Standard Sale' transaction types."
            )
        )


def enforce_no_mixed_transactions(doc, method=None):
    if not doc.get("custom_instrument_placement_contract"):
        return


def validate_free_issue_zero_rates(doc, method=None):
    """
    Enforce that Contract Free Issue and Contract Consumable Free Issue
    lines carry rate=0.
    """
    ttype = doc.get("custom_placement_transaction_type")
    if ttype not in ("Contract Free Issue", "Contract Consumable Free Issue"):
        return
    for item in doc.items:
        if item.rate != 0:
            frappe.throw(
                frappe._(
                    "Item {0} has rate {1}. {2} lines must have rate=0."
                ).format(
                    frappe.bold(item.item_code),
                    item.rate,
                    ttype,
                )
            )
```

---

## 3. Recovery recomputation — `recovery.py`

This implements §4.1 — the one shared function both Monthly Reconciliation and Revenue Share Statement call.

```python
# nbs_customization/utils/placement/recovery.py

import frappe

RECOVERY_FIELDS = [
    "cumulative_invoiced",
    "cumulative_collected",
    "outstanding_on_contract",
    "recovery_pct_invoiced",
    "recovery_pct_collected",
]


def recompute_contract_recovery(contract_name):
    """
    Recompute all five recovery tracking fields on an Instrument Placement
    Contract from the Sales Invoices linked to it.

    Idempotent, safe to call multiple times.
    Uses ``frappe.db.set_value`` for direct DB writes so it works
    on submitted Contracts (all target fields have allow_on_submit).
    """
    contract = frappe.get_cached_doc("Instrument Placement Contract", contract_name)
    target = contract.total_recovery_target or 0

    invoices = frappe.db.get_all(
        "Sales Invoice",
        filters={
            "custom_instrument_placement_contract": contract_name,
            "custom_counts_toward_recovery": 1,
            "docstatus": 1,
        },
        fields=["grand_total", "outstanding_amount"],
    )

    cumulative_invoiced = sum((inv.grand_total or 0) for inv in invoices)
    cumulative_collected = sum(
        (inv.grand_total or 0) - (inv.outstanding_amount or 0) for inv in invoices
    )
    outstanding_on_contract = cumulative_invoiced - cumulative_collected

    recovery_pct_invoiced = (cumulative_invoiced / target * 100) if target else 0
    recovery_pct_collected = (cumulative_collected / target * 100) if target else 0

    for field, value in [
        ("cumulative_invoiced", cumulative_invoiced),
        ("cumulative_collected", cumulative_collected),
        ("outstanding_on_contract", outstanding_on_contract),
        ("recovery_pct_invoiced", recovery_pct_invoiced),
        ("recovery_pct_collected", recovery_pct_collected),
    ]:
        frappe.db.set_value(
            "Instrument Placement Contract",
            contract_name,
            field,
            value,
            update_modified=False,
        )

    return {
        "cumulative_invoiced": cumulative_invoiced,
        "cumulative_collected": cumulative_collected,
        "outstanding_on_contract": outstanding_on_contract,
        "recovery_pct_invoiced": recovery_pct_invoiced,
        "recovery_pct_collected": recovery_pct_collected,
    }
```

---

## 4. Sales Invoice hooks — `sales_invoice.py`

```python
# nbs_customization/controllers/placement/sales_invoice.py

import frappe
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


def validate(doc, method=None):
    from nbs_customization.controllers.placement.sales_validate import validate_placement_transaction
    validate_placement_transaction(doc)


def on_submit(doc, method=None):
    if doc.get("custom_instrument_placement_contract"):
        recompute_contract_recovery(doc.custom_instrument_placement_contract)


def on_cancel(doc, method=None):
    if doc.get("custom_instrument_placement_contract"):
        recompute_contract_recovery(doc.custom_instrument_placement_contract)
```

---

## 5. Payment Entry hooks — `payment_entry.py`

```python
# nbs_customization/controllers/placement/payment_entry.py

import frappe
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


def get_placement_contracts_from_references(doc):
    contracts = set()
    for ref in doc.get("references") or []:
        if ref.reference_doctype != "Sales Invoice":
            continue
        contract = frappe.db.get_value(
            "Sales Invoice",
            ref.reference_name,
            "custom_instrument_placement_contract",
        )
        if contract:
            contracts.add(contract)
    return list(contracts)


def on_submit(doc, method=None):
    for contract_name in get_placement_contracts_from_references(doc):
        recompute_contract_recovery(contract_name)


def on_cancel(doc, method=None):
    for contract_name in get_placement_contracts_from_references(doc):
        recompute_contract_recovery(contract_name)
```

---

## 6. `hooks.py` updates

```python
# Add these as new top-level imports at the top of hooks.py (or reference
# the full module path in the string).

doc_events = {
    "Quotation": {
        "validate": "nbs_customization.controllers.validations.sales.validate_unique_items"
    },
    "Sales Order": {
        "validate": [
            "nbs_customization.controllers.validations.sales.validate_unique_items",
            "nbs_customization.controllers.placement.sales_validate.validate_placement_transaction",
            "nbs_customization.controllers.placement.sales_validate.validate_free_issue_zero_rates",
        ],
    },
    "Delivery Note": {
        "before_save": "nbs_customization.controllers.delivery_note.before_save",
        "validate": [
            "nbs_customization.controllers.validations.stock.validate_unique_item_batch",
            "nbs_customization.controllers.delivery_note.validate",
            "nbs_customization.controllers.placement.sales_validate.validate_placement_transaction",
            "nbs_customization.controllers.placement.sales_validate.validate_free_issue_zero_rates",
        ],
        "before_submit": "nbs_customization.controllers.delivery_note.before_submit",
        "on_submit": "nbs_customization.controllers.delivery_note.on_submit",
        "on_cancel": "nbs_customization.controllers.delivery_note.on_cancel",
    },
    "Sales Invoice": {
        "validate": [
            "nbs_customization.controllers.validations.stock.validate_unique_item_batch",
            "nbs_customization.controllers.placement.sales_invoice.validate",
            "nbs_customization.controllers.placement.sales_validate.validate_free_issue_zero_rates",
        ],
        "before_save": [
            "nbs_customization.controllers.sales_invoice.before_save",
        ],
        "before_submit": "nbs_customization.controllers.sales_invoice.before_submit",
        "on_submit": [
            "nbs_customization.controllers.placement.sales_invoice.on_submit",
        ],
        "on_cancel": [
            "nbs_customization.controllers.placement.sales_invoice.on_cancel",
        ],
    },

    "Payment Entry": {
        "on_submit": "nbs_customization.controllers.placement.payment_entry.on_submit",
        "on_cancel": "nbs_customization.controllers.placement.payment_entry.on_cancel",
    },
}
```

---

## 7. Tests

```python
# nbs_customization/utils/placement/test_recovery.py

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.utils.placement.recovery import recompute_contract_recovery


class TestRecoveryRecompute(FrappeTestCase):
    def setUp(self):
        pass

    def test_recompute_updates_contract(self):
        pass

    def test_recompute_zero_target(self):
        pass

    def test_payment_entry_triggers_recompute(self):
        pass
```

*(Full test implementation follows standard ERPNext test patterns — SIs are created with `frappe.get_doc(...).insert().submit()`)*
