# B3 — Pricing Worksheet Calculation Engine

**Depends on:** B2 (valid items query), B1 (spec data integrity)
**Provides:** Whitelisted method `calculate_worksheet`, controller for `Instrument Pricing Worksheet`

---

## Objective

Implement the full formula chain from §1.4–1.5 as an idempotent, whitelisted calculation method. Must match the worked examples in §1.5 within rounding tolerance.

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/instrument_pricing_worksheet.py` | Create — full controller with calculation engine |
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/test_instrument_pricing_worksheet.py` | Create — tests against §1.5 examples |

---

## 1. Controller — `instrument_pricing_worksheet.py`

All calculation functions live as module-level functions in the same file as the DocType controller, not in a separate `worksheet.py`. They are callable from custom buttons via `@frappe.whitelist()`.

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/instrument_pricing_worksheet.py

import frappe
from frappe.model.document import Document
from math import ceil
from nbs_customization.utils.placement.valid_items import validate_items_belong_to_analyzer


class InstrumentPricingWorksheet(Document):
    def validate(self):
        self._validate_reagent_items()
        self._validate_annual_interest()

    def _validate_reagent_items(self):
        """Every item_code in costing lines must be valid for the analyzer."""
        if not self.analyzer_pid:
            return
        item_codes = [row.item_code for row in self.reagent_costing_lines if row.item_code]
        validate_items_belong_to_analyzer(self.analyzer_pid, item_codes, throw=True)

    def _validate_annual_interest(self):
        """Only editable for RLO, must be positive for RLO."""
        if self.contract_type == "RLO":
            if self.annual_interest_rate is None or self.annual_interest_rate <= 0:
                frappe.throw(
                    frappe._("Annual Interest Rate is required for RLO contracts.")
                )
        else:
            self.annual_interest_rate = 0


# ------------------------------------------------------------------
# Calculation engine (module-level, whitelisted)
# ------------------------------------------------------------------


def calculate_worksheet(worksheet_name):
    """
    Populate all computed fields on an Instrument Pricing Worksheet.
    Idempotent — safe to re-run.
    """
    ws = frappe.get_doc("Instrument Pricing Worksheet", worksheet_name)

    if ws.status not in ("Draft", "Calculated"):
        frappe.throw(
            frappe._("Cannot recalculate a worksheet with status '{0}'.").format(ws.status)
        )

    _compute_lines(ws)
    _compute_rollups(ws)
    _compute_markup_or_revenue_share(ws)

    ws.calculated_by = frappe.session.user
    ws.calculated_date = frappe.utils.today()
    ws.status = "Calculated"

    ws.save(ignore_permissions=True)
    return ws


def _compute_lines(ws):
    """Compute per-line read-only fields."""
    for line in ws.reagent_costing_lines:
        if line.line_type == "Test Reagent":
            line.total_tests_over_term = line.monthly_test_volume * 12 * ws.contract_years
            if line.tests_per_pack:
                line.packs_needed = ceil(line.total_tests_over_term / line.tests_per_pack)
            else:
                line.packs_needed = 0
                frappe.msgprint(
                    frappe._("Line {0}: tests_per_pack is zero. Set packs_needed to 0.").format(line.idx),
                    alert=True, indicator="orange",
                )
            line.total_cost_line = (line.packs_needed or 0) * (line.cogs_per_pack or 0)

            # Revenue share per-line
            if ws.calculation_output_type == "Revenue Share Percentage" and line.test_price:
                line.total_gross_revenue_line = line.total_tests_over_term * line.test_price
            else:
                line.total_gross_revenue_line = 0

        elif line.line_type == "Non-Test Consumable":
            years = ws.contract_years
            freq = line.consumption_frequency
            qty = line.consumption_qty or 0

            if freq == "Per Month":
                line.total_units_over_term = qty * 12 * years
            elif freq == "Per Service Interval":
                line.total_units_over_term = 0
                frappe.msgprint(
                    frappe._(
                        "Line {0}: Consumption frequency is 'Per Service Interval' but no "
                        "service event count is available to compute total consumption. "
                        "Set total_units_over_term manually or change the frequency."
                    ).format(line.idx),
                    alert=True, indicator="orange",
                )
            elif freq == "Per Year":
                line.total_units_over_term = qty * years
            else:
                line.total_units_over_term = 0

            line.total_cost_line = line.total_units_over_term * (line.cogs_per_unit or 0)


def _compute_rollups(ws):
    """Aggregate line totals into the worksheet summary fields."""
    total_reagent_cogs = 0
    total_consumable_cost = 0

    for line in ws.reagent_costing_lines:
        if line.line_type == "Test Reagent":
            total_reagent_cogs += line.total_cost_line or 0
        elif line.line_type == "Non-Test Consumable":
            total_consumable_cost += line.total_cost_line or 0

    ws.total_test_reagent_cogs = total_reagent_cogs
    ws.total_consumable_cost = total_consumable_cost

    # Fixed cost to recover
    interest_factor = 1 + (ws.annual_interest_rate or 0) / 100 * ws.contract_years
    landed = ws.analyzer_landed_cost or 0

    if ws.annual_maintenance_cost_rate and ws.analyzer_landed_cost:
        ws.total_maintenance_cost = (
            (ws.annual_maintenance_cost_rate / 100) * ws.analyzer_landed_cost * ws.contract_years
        )

    ws.fixed_cost_to_recover = (
        landed * interest_factor
        + (ws.total_maintenance_cost or 0)
        + total_consumable_cost
    )

    ws.total_cost_base = ws.fixed_cost_to_recover + total_reagent_cogs
    ws.profit_amount = (ws.profit_margin_pct or 0) / 100 * ws.total_cost_base
    ws.final_revenue_target = ws.total_cost_base + ws.profit_amount


def _compute_markup_or_revenue_share(ws):
    """Final computation depends on calculation_output_type."""
    if ws.calculation_output_type == "Markup Factor on Reagent Price":
        if ws.total_test_reagent_cogs:
            ws.markup_factor = ws.final_revenue_target / ws.total_test_reagent_cogs
        else:
            ws.markup_factor = 0
            frappe.msgprint(
                "Total Test Reagent COGS is zero — markup factor set to 0.",
                alert=True, indicator="orange",
            )

        # Apply markup to each Test Reagent line
        for line in ws.reagent_costing_lines:
            if line.line_type == "Test Reagent":
                line.markup_factor_applied = ws.markup_factor
                line.selling_price_per_pack = (line.cogs_per_pack or 0) * ws.markup_factor
                if line.tests_per_pack:
                    line.selling_price_per_test = line.selling_price_per_pack / line.tests_per_pack
                else:
                    line.selling_price_per_test = 0

    elif ws.calculation_output_type == "Revenue Share Percentage":
        total_gross = sum(
            (line.total_gross_revenue_line or 0)
            for line in ws.reagent_costing_lines
            if line.line_type == "Test Reagent"
        )
        ws.total_gross_test_revenue_over_term = total_gross
        if total_gross:
            ws.required_revenue_share_pct = (ws.final_revenue_target / total_gross) * 100
        else:
            ws.required_revenue_share_pct = 0


@frappe.whitelist()
def calculate_worksheet_wrapper(worksheet_name):
    """Whitelisted entry point — callable from custom button."""
    return calculate_worksheet(worksheet_name)
```

---

## 2. Tests — worked example §1.5

```python
# nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/test_instrument_pricing_worksheet.py

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.nbs_customization.nbs_customization.doctype.instrument_pricing_worksheet.instrument_pricing_worksheet import calculate_worksheet


class TestRRAWorksheet(FrappeTestCase):
    """Chemistry analyzer RRA — must match §1.5 example."""

    def setUp(self):
        self.analyzer = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Chem Analyzer RRA", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)
        self._setup_spec()

        self.reagent = self._make_reagent("ALB", 23.10, 102)

        self.ws = frappe.get_doc({
            "doctype": "Instrument Pricing Worksheet",
            "analyzer_pid": self.analyzer.item_code,
            "contract_type": "RRA",
            "calculation_output_type": "Markup Factor on Reagent Price",
            "analyzer_landed_cost": 8000,
            "contract_years": 3,
            "annual_maintenance_cost_rate": 10,
            "profit_margin_pct": 25,
            "reagent_costing_lines": [
                {
                    "line_type": "Test Reagent",
                    "item_code": self.reagent.item_code,
                    "monthly_test_volume": 102,
                    "cogs_per_pack": 23.10,
                    "tests_per_pack": 100,
                }
            ],
        }).insert()

    def _setup_spec(self):
        param = frappe.get_doc(
            {"doctype": "Test Parameter", "parameter_name": "_TST ALB", "parameter_code": "ALB"}
        ).insert(ignore_if_duplicate=True)
        at = frappe.get_doc(
            {"doctype": "Analyzer Type", "title": "_TST Chemistry"}
        ).insert(ignore_if_duplicate=True)
        frappe.get_doc({
            "doctype": "Instrument Specification",
            "item": self.analyzer.item_code,
            "analyzer_type": at.name,
        }).insert()

    def _make_reagent(self, name, cogs, volume):
        item = frappe.get_doc({
            "doctype": "Item", "item_code": f"_TST {name}", "item_group": "Products"
        }).insert(ignore_if_duplicate=True)
        frappe.get_doc({
            "doctype": "Reagent Specification",
            "item": item.item_code,
            "reagent_role": "Test Reagent",
            "default_cogs_per_pack": cogs,
            "default_tests_per_pack": 100,
        }).insert(ignore_if_duplicate=True)
        return item

    def tearDown(self):
        frappe.db.rollback()

    def test_rra_markup_factor(self):
        calculate_worksheet(self.ws.name)
        self.ws.reload()

        self.assertAlmostEqual(self.ws.analyzer_landed_cost, 8000)
        self.assertEqual(self.ws.total_maintenance_cost, 2400)

        self.assertAlmostEqual(self.ws.total_test_reagent_cogs, 854.70, places=2)
        self.assertAlmostEqual(self.ws.fixed_cost_to_recover, 10400)
        self.assertAlmostEqual(self.ws.total_cost_base, 11254.70, places=2)
        self.assertAlmostEqual(self.ws.profit_amount, 2813.675, places=2)
        self.assertAlmostEqual(self.ws.final_revenue_target, 14068.375, places=2)

        self.assertAlmostEqual(self.ws.markup_factor, 14068.375 / 854.70, places=4)
```

---

## 3. `hooks.py` registration

No `doc_events` needed — the `validate` method fires automatically. The whitelisted method is registered via `@frappe.whitelist()`.
