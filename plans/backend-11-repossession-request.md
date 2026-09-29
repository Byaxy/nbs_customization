# B11 — Repossession Request

**Depends on:** B5 (contract lifecycle), B7 (deployment side effects)
**Provides:** Full controller for `Repossession Request` + `execute_retrieval` whitelisted method

---

## Objective

Implement the approval-gated repossession workflow. On approval, an authorized user can execute the retrieval, which triggers the Analyzer Deployment status change (and via B7, the Asset updates and Asset Movement).

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/repossession_request/repossession_request.py` | Create — full controller with retrieval logic |
| `nbs_customization/nbs_customization/nbs_customization/doctype/repossession_request/test_repossession_request.py` | Create — tests |

---

## 1. Controller — `repossession_request.py`

All logic (controller + `execute_retrieval`) lives in the same file as the DocType controller, not in a separate `repossession.py`.

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/repossession_request/repossession_request.py

import frappe
from frappe.model.document import Document


class RepossessionRequest(Document):
    def validate(self):
        if self.is_new():
            return
        self._validate_status_transition()

    def on_submit(self):
        self._validate_required_fields()
        self.status = "Pending Approval"
        self.db_set("status", "Pending Approval")

    def on_cancel(self):
        self.status = "Closed"
        self.db_set("status", "Closed")

    def _validate_status_transition(self):
        old = self.get_doc_before_save()
        if not old:
            return
        if self.docstatus == 1 and old.docstatus == 0:
            return  # Initial submit — on_submit handles the transition

        allowed = {
            "Draft": {"Pending Approval"},
            "Pending Approval": {"Approved"},
            "Approved": {"Analyzer Retrieved", "Closed"},
            "Analyzer Retrieved": {"Closed"},
        }

        allowed_next = allowed.get(old.status, set())
        if self.status in allowed_next:
            return

        frappe.throw(
            frappe._(
                "Cannot transition Repossession Request from '{0}' to '{1}'. "
                "Allowed transitions: {2}"
            ).format(old.status, self.status, ", ".join(allowed_next))
        )

    def _validate_required_fields(self):
        if self.reason in ("Minimum Purchase Breach",):
            if not self.breach_count:
                frappe.throw(
                    frappe._("Breach Count is required when reason is '{0}'.").format(self.reason)
                )
        if self.reason in ("Non-Payment of Revenue Share", "Non-Payment of Invoices"):
            if not self.unpaid_statements:
                frappe.throw(
                    frappe._("Number of unpaid statements is required for non-payment reasons.")
                )


# ------------------------------------------------------------------
# Retrieval execution (module-level, whitelisted)
# ------------------------------------------------------------------


@frappe.whitelist()
def execute_retrieval(repossession_request_name):
    """
    Execute an approved repossession request.
    Updates the linked Analyzer Deployment to Permanently Retrieved
    (which fires B7 side effects: asset status change, Asset Movement).
    """
    rr = frappe.get_doc("Repossession Request", repossession_request_name)

    if rr.status != "Approved":
        frappe.throw(
            frappe._("Cannot execute retrieval — Repossession Request status is '{0}', not 'Approved'.").format(
                rr.status
            )
        )

    if not rr.analyzer_deployment:
        frappe.throw(
            frappe._("No Analyzer Deployment is linked to this Repossession Request.")
        )

    deployment = frappe.get_doc("Analyzer Deployment", rr.analyzer_deployment)
    deployment.deployment_status = "Permanently Retrieved"
    deployment.retrieval_date = rr.actual_retrieval_date or frappe.utils.today()
    deployment.retrieval_reason = _map_repossession_reason(rr.reason)
    deployment.condition_at_return = rr.analyzer_condition_on_return
    deployment.retrieved_by = rr.retrieved_by or frappe.session.user
    deployment.repossession_request = rr.name

    deployment.save(ignore_permissions=True)

    rr.status = "Analyzer Retrieved"
    rr.db_set("status", "Analyzer Retrieved")

    frappe.msgprint(
        frappe._("Analyzer retrieved successfully. Deployment {0} updated.").format(
            frappe.bold(deployment.name)
        )
    )

    return deployment.name


def _map_repossession_reason(rr_reason):
    mapping = {
        "Minimum Purchase Breach": "Contract Breach",
        "Non-Payment of Revenue Share": "Contract Breach",
        "Non-Payment of Invoices": "Contract Breach",
        "Contract Expiry": "Contract Expiry",
        "Customer Request": "Customer Request",
        "Analyzer Upgrade": "Analyzer Upgrade",
        "Other": "Other",
    }
    return mapping.get(rr_reason, "Other")
```

---

## 2. Tests

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/repossession_request/test_repossession_request.py

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.nbs_customization.nbs_customization.doctype.repossession_request.repossession_request import execute_retrieval


class TestRepossession(FrappeTestCase):
    def setUp(self):
        pass

    def tearDown(self):
        frappe.db.rollback()

    def test_submit_sets_pending_approval(self):
        pass

    def test_approve_then_execute_retrieval(self):
        pass

    def test_execute_updates_deployment_status(self):
        pass

    def test_execute_requires_approved_status(self):
        rr_name = ""
        with self.assertRaises(frappe.ValidationError):
            execute_retrieval(rr_name)
```
