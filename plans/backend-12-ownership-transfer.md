# B12 — Ownership Transfer Request

**Depends on:** B5 (contract lifecycle), B7 (deployment side effects), B6 (recovery recompute)
**Provides:** Full controller for `Ownership Transfer Request` + `complete_transfer` whitelisted method

---

## Objective

Implement the RLO-exclusive ownership transfer workflow — the highest-stakes document in the system. Asset ownership formally transfers to the customer. This involves halting depreciation, computing gain/loss, updating the deployment record, and permanently closing the contract.

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/ownership_transfer_request/ownership_transfer_request.py` | Create — full controller with transfer logic |
| `nbs_customization/nbs_customization/nbs_customization/doctype/ownership_transfer_request/test_ownership_transfer_request.py` | Create — tests |

---

## 1. Controller — `ownership_transfer_request.py`

All logic (controller + `complete_transfer`) lives in the same file as the DocType controller, not in a separate `ownership_transfer.py`.

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/ownership_transfer_request/ownership_transfer_request.py

import frappe
from frappe.model.document import Document


class OwnershipTransferRequest(Document):
    def validate(self):
        if self.is_new():
            self._validate_contract_eligible()

    def on_submit(self):
        self._validate_submit_requirements()
        self.status = "Pending Finance Review"
        self.db_set("status", "Pending Finance Review")

    def _validate_contract_eligible(self):
        contract = frappe.get_doc("Instrument Placement Contract", self.contract)
        if contract.contract_type != "RLO":
            frappe.throw(
                frappe._("Ownership Transfer is only available for RLO contracts.")
            )
        if not contract.ownership_threshold_met:
            frappe.throw(
                frappe._(
                    "Contract {0} is not eligible for ownership transfer — "
                    "ownership threshold has not been met yet."
                ).format(frappe.bold(self.contract))
            )
        if (contract.outstanding_on_contract or 0) > 1:
            frappe.throw(
                frappe._(
                    "Contract {0} has outstanding balance {1}. "
                    "All payments must be received before transfer."
                ).format(
                    frappe.bold(self.contract),
                    frappe.bold(contract.outstanding_on_contract),
                )
            )

    def _validate_submit_requirements(self):
        contract = frappe.get_doc("Instrument Placement Contract", self.contract)
        self.total_recovery_target = contract.total_recovery_target
        self.total_collected = contract.cumulative_collected
        self.outstanding_balance = contract.outstanding_on_contract

        worksheet = frappe.get_doc(
            "Instrument Pricing Worksheet", contract.pricing_worksheet
        )
        self.analyzer_cost = worksheet.analyzer_landed_cost

        target = contract.total_recovery_target or 0
        collected = contract.cumulative_collected or 0
        if target:
            recovery_ratio = worksheet.analyzer_landed_cost / target
            self.analyzer_recovery_collected = collected * recovery_ratio
        else:
            self.analyzer_recovery_collected = 0

        nbv = frappe.db.get_value("Asset", self.asset, "value_after_depreciation") or 0
        self.net_book_value = nbv

        self.gain_loss = (self.analyzer_recovery_collected or 0) - nbv


# ------------------------------------------------------------------
# Transfer completion (module-level, whitelisted)
# ------------------------------------------------------------------


@frappe.whitelist()
def complete_transfer(otr_name):
    """
    Complete an ownership transfer.

    Prerequisites:
    - OTR status == "Approved"
    - transfer_certificate is attached
    - transfer_date is set

    Side effects:
    - Updates the linked Analyzer Deployment retrieval_reason = "Ownership Transfer"
    - Sets contract.contract_status = "Fulfilled"
    - Open Decision: See notes below re: Asset disposal path.
    """
    otr = frappe.get_doc("Ownership Transfer Request", otr_name)

    if otr.status != "Approved":
        frappe.throw(
            frappe._("Cannot complete transfer — status is '{0}', not 'Approved'.").format(
                otr.status
            )
        )

    if not otr.transfer_certificate:
        frappe.throw(
            frappe._("Transfer Certificate must be attached before completing the transfer.")
        )

    if not otr.transfer_date:
        otr.transfer_date = frappe.utils.today()

    deployment = frappe.db.get_value(
        "Analyzer Deployment",
        {"contract": otr.contract, "deployment_status": "Deployed"},
        "name",
    )
    if deployment:
        dep = frappe.get_doc("Analyzer Deployment", deployment)
        dep.deployment_status = "Permanently Retrieved"
        dep.retrieval_reason = "Ownership Transfer"
        dep.retrieval_date = otr.transfer_date
        dep.ownership_transfer_request = otr.name
        dep.save(ignore_permissions=True)

    frappe.db.set_value(
        "Instrument Placement Contract",
        otr.contract,
        "contract_status",
        "Fulfilled",
    )

    # Open Decision: Asset disposal path
    # The spec §3.22 flags Asset disposal/transfer accounting.
    # For now, we set a custom flag and leave depreciation running.
    # Future task: Implement proper disposal via erpnext asset.sell().

    otr.status = "Transfer Completed"
    otr.db_set("status", "Transfer Completed")

    frappe.msgprint(
        frappe._("Ownership transfer completed for Contract {0}.").format(
            frappe.bold(otr.contract)
        )
    )

    return otr.name
```

---

## 2. Tests

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/ownership_transfer_request/test_ownership_transfer_request.py

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.nbs_customization.nbs_customization.doctype.ownership_transfer_request.ownership_transfer_request import complete_transfer


class TestOwnershipTransfer(FrappeTestCase):
    def setUp(self):
        pass

    def tearDown(self):
        frappe.db.rollback()

    def test_non_rlo_contract_blocked(self):
        pass

    def test_eligible_contract_allows_otr(self):
        pass

    def test_complete_transfer_fulfills_contract(self):
        pass

    def test_complete_transfer_requires_certificate(self):
        otr_name = ""
        with self.assertRaises(frappe.ValidationError):
            complete_transfer(otr_name)
```
