# B1 — Specification Layer Validations

**Depends on:** Nothing (first backend task)
**Provides:** DocType controller logic for `Instrument Specification` and `Reagent Specification`

---

## Objective

Add server-side validation to the two master-data specifications that back every pricing and contract decision downstream. These prevent data corruption at the source so that every downstream DocType (Worksheet, Contract, Sales Invoice) can trust the spec records it references.

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_specification/instrument_specification.py` | Create — controller |
| `nbs_customization/nbs_customization/nbs_customization/doctype/reagent_specification/reagent_specification.py` | Create — controller |
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_specification/test_instrument_specification.py` | Create — tests for Instrument Spec controller |
| `nbs_customization/nbs_customization/nbs_customization/doctype/reagent_specification/test_reagent_specification.py` | Create — tests for Reagent Spec controller |

---

## 1. `Instrument Specification` controller

Create the file at the existing doctype path. Follow the same skeleton as the existing placement controllers (currently all `class X(Document): pass` — this adds actual logic).

```python
# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InstrumentSpecification(Document):
    def validate(self):
        self._validate_no_duplicate_test_parameters()
        self._validate_reagent_is_test_reagent()

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    def _validate_no_duplicate_test_parameters(self):
        seen = set()
        for row in self.get("supported_test_methods") or []:
            if not row.test_parameter:
                continue
            if row.test_parameter in seen:
                frappe.throw(
                    frappe._("Test Parameter {0} appears more than once in Supported Test Methods.")
                    .format(frappe.bold(row.test_parameter))
                )
            seen.add(row.test_parameter)

    def _validate_reagent_is_test_reagent(self):
        for row in self.get("supported_test_methods") or []:
            if not row.required_reagent:
                continue
            rs = frappe.db.get_value(
                "Reagent Specification",
                {"item": row.required_reagent},
                "reagent_role",
            )
            if rs is None:
                frappe.msgprint(
                    frappe._(
                        "Item {0} has no Reagent Specification. Ensure it is set up before using "
                        "this specification in a Worksheet or Contract."
                    ).format(frappe.bold(row.required_reagent)),
                    alert=True,
                    indicator="orange",
                )
                continue
            if rs != "Test Reagent":
                frappe.throw(
                    frappe._(
                        "Item {0} has Reagent Role '{1}', but only items with "
                        "Reagent Role 'Test Reagent' are allowed in Supported Test Methods."
                    ).format(frappe.bold(row.required_reagent), rs)
                )
```

### Design notes

- Uses `frappe.db.get_value` (single-field, single-row fetch) rather than loading full documents — pattern used throughout ERPNext for cross-validation in `validate()` hooks where performance matters.
- The warning (not error) when no Reagent Spec exists is an intentional concession to setup-order flexibility: a user might create the Instrument Spec before all reagent Items have their Reagent Specs. The downstream Worksheet/Contract controllers (B3, B4, B5) will enforce the hard constraint at the point where live pricing is computed, so this is safe.
- Following the existing app convention of private `_validate_*` methods rather than inlining everything into `validate`.

---

## 2. `Reagent Specification` controller

The sensitive validation here is: if `reagent_role` changes on a record that's already referenced by an active downstream document, the existing pricing/contract data breaks.

**Open Decision confirmed:** The spec says an edge case exists but explicitly flags it as an open decision. Per my proposal (endorsed by the spec's own recommendation): **block the role change** with a clear error listing the referencing documents. Rationale: a silent role flip from "Test Reagent" to "Non-Test Consumable" on an item used in an active Contract would invalidate every `Contract Reagent Line` that treats it as a Test Reagent with `contract_price`, `min_monthly_qty`, etc. — data integrity violation with real financial consequences. The user is better served by a hard block and a manual process (amend the contract first, then change the role).

```python
# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReagentSpecification(Document):
    def validate(self):
        if self.is_new() or not self.has_value_changed("reagent_role"):
            return
        self._validate_no_active_downstream_references()

    def _validate_no_active_downstream_references(self):
        item = self.item
        refs = []

        ipw_names = frappe.db.get_all(
            "Reagent Costing Line",
            filters={"item_code": item, "parenttype": "Instrument Pricing Worksheet"},
            pluck="parent",
            distinct=True,
        )
        if ipw_names:
            active_ipws = frappe.db.get_all(
                "Instrument Pricing Worksheet",
                filters=[
                    ["name", "in", ipw_names],
                    ["status", "!=", "Draft"],
                ],
                pluck="name",
            )
            for name in active_ipws:
                refs.append(("Instrument Pricing Worksheet", name))

        crl_names = frappe.db.get_all(
            "Contract Reagent Line",
            filters={"item_code": item, "parenttype": "Instrument Placement Contract"},
            pluck="parent",
            distinct=True,
        )
        if crl_names:
            active_contracts = frappe.db.get_all(
                "Instrument Placement Contract",
                filters=[
                    ["name", "in", crl_names],
                    ["contract_status", "in", ["Active", "Fulfilled", "Breached"]],
                ],
                pluck="name",
            )
            for name in active_contracts:
                refs.append(("Instrument Placement Contract", name))

        if not refs:
            return

        msg_parts = [
            frappe._(
                "Cannot change Reagent Role from '{0}' to '{1}' because this item is "
                "referenced by the following active documents:"
            ).format(
                frappe.bold(self.get_doc_before_save().reagent_role),
                frappe.bold(self.reagent_role),
            )
        ]
        for dt, dn in refs:
            msg_parts.append(f"<li>{dt}: {dn}</li>")

        frappe.throw(
            "<ol>" + "".join(msg_parts) + "</ol>",
            title=frappe._("Reagent Role Change Blocked"),
        )
```

### Design notes

- `has_value_changed` and `get_doc_before_save()` are standard Frappe Document lifecycle APIs — studied in `frappe.model.document.Document`.

---

## 3. Tests

### `test_instrument_specification.py`

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/instrument_specification/test_instrument_specification.py

import frappe
from frappe.tests.utils import FrappeTestCase


class TestInstrumentSpecification(FrappeTestCase):
    def setUp(self):
        self.test_item = frappe.get_doc(
            {"doctype": "Item", "item_code": "_Test Analyzer for Spec Validation", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)
        self.test_reagent = frappe.get_doc(
            {"doctype": "Item", "item_code": "_Test Reagent for Spec Validation", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)
        frappe.get_doc(
            {
                "doctype": "Reagent Specification",
                "item": self.test_reagent.item_code,
                "reagent_role": "Test Reagent",
                "default_tests_per_pack": 100,
                "default_cogs_per_pack": 50,
            }
        ).insert(ignore_if_duplicate=True)

        self.test_param = frappe.get_doc(
            {"doctype": "Test Parameter", "parameter_name": "_Test Param for Spec Valid", "parameter_code": "TVAL"}
        ).insert(ignore_if_duplicate=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_duplicate_test_parameter_blocked(self):
        doc = frappe.get_doc(
            {
                "doctype": "Instrument Specification",
                "item": self.test_item.item_code,
                "supported_test_methods": [
                    {"test_parameter": self.test_param.name, "required_reagent": self.test_reagent.item_code},
                    {"test_parameter": self.test_param.name, "required_reagent": self.test_reagent.item_code},
                ],
            }
        )
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_reagent_role_mismatch_blocked(self):
        consumable = frappe.get_doc(
            {"doctype": "Item", "item_code": "_Test Consumable for Spec", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)
        frappe.get_doc(
            {
                "doctype": "Reagent Specification",
                "item": consumable.item_code,
                "reagent_role": "Non-Test Consumable",
            }
        ).insert(ignore_if_duplicate=True)

        doc = frappe.get_doc(
            {
                "doctype": "Instrument Specification",
                "item": self.test_item.item_code,
                "supported_test_methods": [
                    {"test_parameter": self.test_param.name, "required_reagent": consumable.item_code},
                ],
            }
        )
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_pass_with_valid_reagent(self):
        doc = frappe.get_doc(
            {
                "doctype": "Instrument Specification",
                "item": self.test_item.item_code,
                "supported_test_methods": [
                    {"test_parameter": self.test_param.name, "required_reagent": self.test_reagent.item_code},
                ],
            }
        )
        doc.insert()
        self.assertTrue(doc.name)
```

### `test_reagent_specification.py`

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/reagent_specification/test_reagent_specification.py

import frappe
from frappe.tests.utils import FrappeTestCase


class TestReagentSpecification(FrappeTestCase):
    def setUp(self):
        self.reagent_item = frappe.get_doc(
            {"doctype": "Item", "item_code": "_Test RSpec Role Item", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)
        self.rs = frappe.get_doc(
            {
                "doctype": "Reagent Specification",
                "item": self.reagent_item.item_code,
                "reagent_role": "Test Reagent",
                "default_tests_per_pack": 100,
                "default_cogs_per_pack": 50,
            }
        ).insert()

    def tearDown(self):
        frappe.db.rollback()

    def test_role_change_blocked_when_referenced_by_active_worksheet(self):
        analyzer = frappe.get_doc(
            {"doctype": "Item", "item_code": "_Test Analyzer for RSpec", "item_group": "Products"}
        ).insert()

        # Instrument Specification needed so B3's validate passes
        param = frappe.get_doc(
            {"doctype": "Test Parameter", "parameter_name": "_TST RSpec Param", "parameter_code": "RSPC"}
        ).insert(ignore_if_duplicate=True)
        frappe.get_doc({
            "doctype": "Instrument Specification",
            "item": analyzer.item_code,
            "supported_test_methods": [
                {"test_parameter": param.name, "required_reagent": self.reagent_item.item_code},
            ],
        }).insert()

        ws = frappe.get_doc(
            {
                "doctype": "Instrument Pricing Worksheet",
                "analyzer_pid": analyzer.item_code,
                "contract_type": "RRA",
                "calculation_output_type": "Markup Factor on Reagent Price",
                "analyzer_landed_cost": 1000,
                "contract_years": 1,
                "reagent_costing_lines": [
                    {
                        "line_type": "Test Reagent",
                        "item_code": self.reagent_item.item_code,
                    }
                ],
            }
        ).insert()
        ws.status = "Approved"
        ws.save()

        self.rs.reagent_role = "Non-Test Consumable"
        self.assertRaises(frappe.ValidationError, self.rs.save)

        ws.delete()

    def test_role_change_allowed_when_no_references(self):
        self.rs.reagent_role = "Non-Test Consumable"
        try:
            self.rs.save()
        except frappe.ValidationError:
            self.fail("Role change should have been allowed with no downstream refs")
```

---

## 4. `hooks.py` registration

No `doc_events` entries are needed here — these are DocType controller methods that fire automatically via Frappe's document lifecycle (`validate`). No changes to `hooks.py`.

---

## Verification

```bash
bench --site nbsolutions.localhost run-tests --app nbs_customization --module nbs_customization.nbs_customization.doctype.instrument_specification.test_instrument_specification
bench --site nbsolutions.localhost run-tests --app nbs_customization --module nbs_customization.nbs_customization.doctype.reagent_specification.test_reagent_specification
```
