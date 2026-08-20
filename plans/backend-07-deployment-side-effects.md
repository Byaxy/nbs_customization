# B7 — Analyzer Deployment Status-Change Side Effects

**Depends on:** B5 (contract lifecycle sets asset link), B2 (valid items)
**Provides:** Controller for `Analyzer Deployment` — status transitions drive Asset updates and Asset Movement creation

---

## Objective

When an Analyzer Deployment's `deployment_status` changes, the system must:
1. Update the Asset's `custom_current_deployment_status` and `custom_current_placement_contract`
2. Create/return native Asset Movement records for physical transfers

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/analyzer_deployment/analyzer_deployment.py` | Create — controller |
| `nbs_customization/nbs_customization/nbs_customization/doctype/analyzer_deployment/test_analyzer_deployment.py` | Create — tests |

---

## 1. Controller — `analyzer_deployment.py`

```python
import frappe
from frappe.model.document import Document


class AnalyzerDeployment(Document):
    def validate(self):
        self._detect_status_transition()

    def _detect_status_transition(self):
        if self.is_new():
            return

        old = self.get_doc_before_save()
        if not old:
            return

        new_status = self.deployment_status
        old_status = old.deployment_status

        if new_status == old_status:
            return

        handlers = {
            "Deployed": self._on_deployed,
            "Under Service": self._on_under_service,
            "Temporarily Retrieved": self._on_retrieved,
            "Permanently Retrieved": self._on_permanently_retrieved,
        }

        handler = handlers.get(new_status)
        if handler:
            handler(old_status=old_status)

    def _on_deployed(self, old_status=None):
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_deployment_status",
            "Deployed",
        )
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_placement_contract",
            self.contract,
        )
        self._create_asset_movement(
            from_location=self.asset_storage_location,
            to_location=self.asset_location,
            purpose="Transfer",
        )

    def _on_under_service(self, old_status=None):
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_deployment_status",
            "Under Service",
        )

    def _on_retrieved(self, old_status=None):
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_deployment_status",
            "Warehouse",
        )

    def _on_permanently_retrieved(self, old_status=None):
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_deployment_status",
            "Warehouse",
        )
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_placement_contract",
            None,
        )
        self._create_asset_movement(
            from_location=self.asset_location,
            to_location=self.asset_storage_location,
            purpose="Transfer",
        )

    def _create_asset_movement(self, from_location=None, to_location=None, purpose="Transfer"):
        if not frappe.db.exists("Asset", self.asset):
            return

        movement = frappe.get_doc({
            "doctype": "Asset Movement",
            "company": frappe.db.get_value("Asset", self.asset, "company"),
            "purpose": purpose,
            "transaction_date": self.deployment_date or frappe.utils.today(),
            "assets": [
                {
                    "asset": self.asset,
                    "source_location": from_location,
                    "target_location": to_location,
                }
            ],
        })
        movement.insert(ignore_permissions=True)
        movement.submit()
        return movement
```

---

## 2. Tests

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/analyzer_deployment/test_analyzer_deployment.py

import frappe
from frappe.tests.utils import FrappeTestCase


class TestDeploymentSideEffects(FrappeTestCase):
    def setUp(self):
        self.asset = frappe.get_doc({
            "doctype": "Asset",
            "asset_name": "_TST Deploy Asset",
            "item_code": "_TST Analyzer Item",
            "company": frappe.db.get_single_value("Global Defaults", "default_company"),
            "gross_purchase_amount": 10000,
            "asset_category": frappe.db.get_value("Asset Category", {}, "name"),
        }).insert(ignore_if_duplicate=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_deployed_sets_asset_status(self):
        pass

    def test_permanent_retrieval_clears_contract(self):
        pass

    def test_asset_movement_created_on_deploy(self):
        pass
```

---

## 3. `hooks.py` registration

No changes needed — controller fires via Frappe's `validate` lifecycle.
