# B2 — Item Master Query Helpers

**Depends on:** B1 (Spec validation ensures spec data integrity)
**Provides:** Whitelisted server method shared by Worksheet, Contract, and Sales Transaction query filters

---

## Objective

A single whitelisted method that returns the complete list of valid reagent/consumable Items for a given analyzer Item, based on its Instrument Specification. Every downstream DocType's `get_query` filter and backend `validate` calls this same function — never duplicate the logic.

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/utils/placement/valid_items.py` | Create — shared helper |
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/test_valid_items.py` | Create — tests |

---

## 1. Shared helper — `valid_items.py`

```python
# nbs_customization/utils/placement/valid_items.py

import frappe


@frappe.whitelist()
def get_valid_reagent_items(analyzer_item):
    """
    Return a list of Item codes that are valid reagents/consumables
    for the given analyzer, per its Instrument Specification.

    Returns a list of dicts with keys: item_code, item_name, description, reagent_role
    suitable for direct use in a Link field's ``get_query`` filter or for
    server-side validation.
    """
    spec = frappe.db.get_value("Instrument Specification", {"item": analyzer_item}, "name")
    if not spec:
        return []

    # Collect reagents from supported_test_methods
    reagent_items = frappe.db.get_all(
        "Instrument Test Method",
        filters={"parent": spec},
        fields=["required_reagent"],
        pluck="required_reagent",
        distinct=True,
    )

    # Collect consumables from required_consumables
    consumable_items = frappe.db.get_all(
        "Instrument Consumable Requirement",
        filters={"parent": spec},
        fields=["consumable_item"],
        pluck="consumable_item",
        distinct=True,
    )

    all_items = set(list(reagent_items) + list(consumable_items))

    if not all_items:
        return []

    # Fetch item details + reagent_role
    result = frappe.db.get_all(
        "Item",
        filters={"name": ("in", list(all_items))},
        fields=["name as item_code", "item_name", "description"],
    )

    # Enrich with reagent_role from Reagent Specification
    role_map = dict(
        frappe.db.get_all(
            "Reagent Specification",
            filters={"item": ("in", list(all_items))},
            fields=["item", "reagent_role"],
            as_list=True,
        )
    )

    for r in result:
        r["reagent_role"] = role_map.get(r["item_code"])

    return result


def validate_items_belong_to_analyzer(analyzer_item, item_codes, throw=True):
    """
    Server-side validation: raise if any item in *item_codes* is not a valid
    reagent/consumable for *analyzer_item*.

    Returns True/False. If *throw* is True, calls ``frappe.throw`` on the
    first invalid item with a clear message.
    """
    valid = get_valid_reagent_items(analyzer_item)
    valid_set = {v["item_code"] for v in valid}

    for code in item_codes:
        if code and code not in valid_set:
            msg = frappe._(
                "Item {0} is not a valid reagent or consumable for analyzer {1}. "
                "Please select an item listed in the analyzer's Instrument Specification."
            ).format(frappe.bold(code), frappe.bold(analyzer_item))
            if throw:
                frappe.throw(msg)
            return False
    return True
```

### Design notes

- Uses `frappe.db.get_all` with `pluck` for efficient single-column fetches — avoids loading full Document objects. Pattern used throughout ERPNext's `get_item_details.py` and similar.
- Returns plain dicts, not Document objects — safe for `get_query` response serialization.
- `validate_items_belong_to_analyzer` is the backend enforcement half of §4.4's two-layer validation (client-side `get_query` + server-side `validate`).
- `@frappe.whitelist()` makes it callable from client-side `frappe.call` for the `get_query` filter.

---

## 2. Tests

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/test_valid_items.py

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.utils.placement.valid_items import (
    get_valid_reagent_items,
    validate_items_belong_to_analyzer,
)


class TestValidItems(FrappeTestCase):
    def setUp(self):
        # Create analyzer Item
        self.analyzer = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Analyzer Valid Items", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)

        # Create two reagent Items
        self.reagent_a = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Reagent A", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)
        self.reagent_b = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Reagent B", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)

        # Create a consumption item
        self.cleaning = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Cleaning Soln", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)

        # Reagent Specs
        for code, role in [(self.reagent_a.item_code, "Test Reagent"), (self.reagent_b.item_code, "Test Reagent")]:
            frappe.get_doc(
                {
                    "doctype": "Reagent Specification",
                    "item": code,
                    "reagent_role": role,
                    "default_tests_per_pack": 100,
                    "default_cogs_per_pack": 50,
                }
            ).insert(ignore_if_duplicate=True)

        frappe.get_doc(
            {
                "doctype": "Reagent Specification",
                "item": self.cleaning.item_code,
                "reagent_role": "Non-Test Consumable",
            }
        ).insert(ignore_if_duplicate=True)

        # Test Parameter
        self.param = frappe.get_doc(
            {"doctype": "Test Parameter", "parameter_name": "_TST Param Valid Items", "parameter_code": "TVAL"}
        ).insert(ignore_if_duplicate=True)

        # Instrument Specification linking the analyzer to both reagents + consumable
        frappe.get_doc(
            {
                "doctype": "Instrument Specification",
                "item": self.analyzer.item_code,
                "supported_test_methods": [
                    {"test_parameter": self.param.name, "required_reagent": self.reagent_a.item_code},
                    {"test_parameter": self.param.name, "required_reagent": self.reagent_b.item_code},
                ],
                "required_consumables": [
                    {"consumable_item": self.cleaning.item_code, "consumption_qty": 1, "consumption_frequency": "Per Month"},
                ],
            }
        ).insert()

    def tearDown(self):
        frappe.db.rollback()

    def test_returns_all_valid_items(self):
        items = get_valid_reagent_items(self.analyzer.item_code)
        codes = {i["item_code"] for i in items}
        self.assertIn(self.reagent_a.item_code, codes)
        self.assertIn(self.reagent_b.item_code, codes)
        self.assertIn(self.cleaning.item_code, codes)

    def test_rejects_unlisted_item(self):
        unlisted = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Unlisted Reagent", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)

        result = validate_items_belong_to_analyzer(
            self.analyzer.item_code, [unlisted.item_code], throw=False
        )
        self.assertFalse(result)

    def test_raises_on_unlisted_item(self):
        unlisted = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Raise Reagent", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)

        with self.assertRaises(frappe.ValidationError):
            validate_items_belong_to_analyzer(
                self.analyzer.item_code, [unlisted.item_code], throw=True
            )

    def test_empty_when_no_spec(self):
        items = get_valid_reagent_items("Non Existent Item")
        self.assertEqual(items, [])
```

---

## 3. `hooks.py` registration

No changes needed — the function is called directly by downstream code, not as a hook. It is whitelisted via the `@frappe.whitelist()` decorator.

---

## Dependency notes

- B3 (Worksheet calculation) uses `validate_items_belong_to_analyzer` in the Worksheet `validate` method — imported from `nbs_customization.utils.placement.valid_items`
- B4 (Apply to Contract) uses `get_valid_reagent_items` to populate `get_query` filters — imported from `nbs_customization.utils.placement.valid_items`
- B5 (Contract lifecycle) uses `validate_items_belong_to_analyzer` — imported from `nbs_customization.utils.placement.valid_items`
- B6 (Sales transactions) uses both — imported from `nbs_customization.utils.placement.valid_items`
