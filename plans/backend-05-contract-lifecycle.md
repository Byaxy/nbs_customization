# B5 — Contract Lifecycle

**Depends on:** B2 (valid items), B3 (worksheet calc), B4 (worksheet → contract)
**Provides:** Full controller for `Instrument Placement Contract` — validate, before_submit, on_submit, on_cancel

---

## Objective

Implement the contract's document lifecycle, enforcing business rules at each stage. This is the commercial hub — correctness here protects every downstream process.

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_placement_contract/instrument_placement_contract.py` | Modify — full controller |
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_placement_contract/test_instrument_placement_contract.py` | Create — tests |

---

## 1. Controller — `instrument_placement_contract.py`

```python
import frappe
from frappe.model.document import Document
from nbs_customization.utils.placement.valid_items import validate_items_belong_to_analyzer
from datetime import date


class InstrumentPlacementContract(Document):
    def validate(self):
        self._validate_contract_lines()
        self._compute_duration()
        self._compute_cpt_fields()
        self._validate_pricing_worksheet_link()

    def before_submit(self):
        self._require_declared_volume()
        self._require_pricing_worksheet()
        self._require_contract_lines()

    def on_submit(self):
        self._activate_contract()

    def on_cancel(self):
        self._validate_no_deployment()
        self._clear_asset_link()

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    def _validate_contract_lines(self):
        if not self.analyzer_pid:
            return
        item_codes = [row.item_code for row in self.contract_lines if row.item_code]
        validate_items_belong_to_analyzer(self.analyzer_pid, item_codes, throw=True)

        for line in self.contract_lines:
            if line.contract_price and line.standard_price:
                line.price_uplift = line.contract_price - line.standard_price
            else:
                line.price_uplift = 0

    def _compute_duration(self):
        if self.start_date and self.end_date:
            delta = (
                (self.end_date.year - self.start_date.year) * 12
                + (self.end_date.month - self.start_date.month)
            )
            self.contract_duration_months = max(delta + 1, 0)

    def _compute_cpt_fields(self):
        if self.contract_type != "CPT":
            return
        vol = self.declared_monthly_test_volume or 0
        price = self.agreed_test_price or 0
        pct = (self.revenue_share_pct or 0) / 100

        self.fixed_monthly_gross_revenue = vol * price
        self.fixed_monthly_share_amount = self.fixed_monthly_gross_revenue * pct

    def _validate_pricing_worksheet_link(self):
        if not self.pricing_worksheet:
            return
        ws_status = frappe.db.get_value(
            "Instrument Pricing Worksheet", self.pricing_worksheet, "status"
        )
        if ws_status not in ("Approved", "Applied to Contract"):
            frappe.throw(
                frappe._(
                    "Linked Pricing Worksheet {0} has status '{1}'. "
                    "Only Approved or Applied worksheets can be linked."
                ).format(frappe.bold(self.pricing_worksheet), ws_status)
            )

    # ------------------------------------------------------------------
    # Pre-submit guards
    # ------------------------------------------------------------------

    def _require_declared_volume(self):
        if not self.declared_monthly_test_volume or self.declared_monthly_test_volume <= 0:
            frappe.throw(
                frappe._("Declared Monthly Test Volume must be set and > 0 before submission.")
            )

    def _require_pricing_worksheet(self):
        if not self.pricing_worksheet:
            frappe.throw(
                frappe._("A Pricing Worksheet must be linked before submission.")
            )

    def _require_contract_lines(self):
        if not self.contract_lines or len(self.contract_lines) == 0:
            frappe.throw(
                frappe._("At least one Contract Line is required before submission.")
            )

    # ------------------------------------------------------------------
    # Post-submit actions
    # ------------------------------------------------------------------

    def _activate_contract(self):
        self.contract_status = "Active"
        self.db_set("contract_status", "Active")

        if self.asset:
            frappe.db.set_value(
                "Asset",
                self.asset,
                "custom_current_placement_contract",
                self.name,
            )

    # ------------------------------------------------------------------
    # Cancel guards + cleanup
    # ------------------------------------------------------------------

    def _validate_no_deployment(self):
        deployment = frappe.db.get_value(
            "Analyzer Deployment",
            {"contract": self.name, "deployment_status": ("!=", "Permanently Retrieved")},
            "name",
        )
        if deployment:
            frappe.throw(
                frappe._(
                    "Cannot cancel Contract {0} — Analyzer Deployment {1} exists "
                    "and has not been permanently retrieved. Retrieve the analyzer first."
                ).format(frappe.bold(self.name), frappe.bold(deployment)),
                title=frappe._("Active Deployment Exists"),
            )

    def _clear_asset_link(self):
        if self.asset:
            frappe.db.set_value(
                "Asset",
                self.asset,
                "custom_current_placement_contract",
                None,
            )
```

---

## 2. Tests

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/instrument_placement_contract/test_instrument_placement_contract.py

import frappe
from frappe.tests.utils import FrappeTestCase


class TestContractLifecycle(FrappeTestCase):
    def setUp(self):
        self.analyzer = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST CL Analyzer", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)
        at = frappe.get_doc(
            {"doctype": "Analyzer Type", "title": "_TST CL Chem"}
        ).insert(ignore_if_duplicate=True)
        param = frappe.get_doc(
            {"doctype": "Test Parameter", "parameter_name": "_TST CL Param", "parameter_code": "CL"}
        ).insert(ignore_if_duplicate=True)
        frappe.get_doc({
            "doctype": "Instrument Specification",
            "item": self.analyzer.item_code,
            "analyzer_type": at.name,
        }).insert()

        self.reagent = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST CL Reagent", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)
        frappe.get_doc({
            "doctype": "Reagent Specification",
            "item": self.reagent.item_code,
            "reagent_role": "Test Reagent",
            "default_cogs_per_pack": 50,
            "default_tests_per_pack": 100,
        }).insert(ignore_if_duplicate=True)

        self.customer = frappe.get_doc({
            "doctype": "Customer", "customer_name": "_TST CL Customer", "customer_type": "Company"
        }).insert(ignore_if_duplicate=True)

        ws = frappe.get_doc({
            "doctype": "Instrument Pricing Worksheet",
            "analyzer_pid": self.analyzer.item_code,
            "contract_type": "RRA",
            "calculation_output_type": "Markup Factor on Reagent Price",
            "analyzer_landed_cost": 5000,
            "contract_years": 2,
            "profit_margin_pct": 20,
            "customer": self.customer.name,
            "status": "Approved",
            "reagent_costing_lines": [
                {
                    "line_type": "Test Reagent",
                    "item_code": self.reagent.item_code,
                    "monthly_test_volume": 50,
                    "cogs_per_pack": 50,
                    "tests_per_pack": 100,
                }
            ],
        }).insert()
        self.worksheet = ws

    def tearDown(self):
        frappe.db.rollback()

    def _make_contract(self, **overrides):
        data = {
            "doctype": "Instrument Placement Contract",
            "contract_title": "_TST Contract",
            "contract_type": "RRA",
            "customer": self.customer.name,
            "asset": None,
            "analyzer_pid": self.analyzer.item_code,
            "pricing_worksheet": self.worksheet.name,
            "start_date": "2026-01-01",
            "end_date": "2027-12-31",
            "declared_monthly_test_volume": 100,
            "contract_lines": [
                {
                    "line_type": "Test Reagent",
                    "item_code": self.reagent.item_code,
                    "contract_price": 150,
                    "standard_price": 50,
                }
            ],
        }
        data.update(overrides)
        doc = frappe.get_doc(data).insert()
        return doc

    def test_validate_reagent_restriction(self):
        invalid_item = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Invalid Reagent", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)
        with self.assertRaises(frappe.ValidationError):
            self._make_contract(contract_lines=[
                {"line_type": "Test Reagent", "item_code": invalid_item.item_code, "contract_price": 100},
            ])

    def test_duration_computed(self):
        doc = self._make_contract()
        self.assertEqual(doc.contract_duration_months, 24)

    def test_submit_requires_volume(self):
        doc = self._make_contract(declared_monthly_test_volume=0)
        with self.assertRaises(frappe.ValidationError):
            doc.submit()

    def test_submit_sets_active(self):
        doc = self._make_contract()
        doc.submit()
        self.assertEqual(doc.contract_status, "Active")

    def test_cancel_requires_no_deployment(self):
        doc = self._make_contract()
        doc.submit()
        doc.cancel()
        self.assertEqual(doc.docstatus, 2)
```

---

## 3. `hooks.py` registration

No changes needed — the controller methods fire automatically.
