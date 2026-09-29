# B4 — Apply Worksheet to Contract

**Depends on:** B2 (valid items), B3 (worksheet calculation)
**Provides:** Whitelisted method `apply_worksheet_to_contract` that creates an `Instrument Placement Contract` from an approved `Instrument Pricing Worksheet`

---

## Objective

When the user clicks "Apply to Contract" on an Approved worksheet, this method:
1. Creates a draft `Instrument Placement Contract` with all lines mapped
2. Programmatically creates a dedicated Price List + Item Price records
3. Sets `contract_price_list` on the Contract
4. Marks the Worksheet as "Applied to Contract"

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/instrument_pricing_worksheet.py` | Modify — add `apply_worksheet_to_contract` |
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/test_instrument_pricing_worksheet.py` | Modify — add tests for apply |

---

## 1. `apply_worksheet_to_contract` — in `instrument_pricing_worksheet.py`

Add these functions to the same file as the calculation engine (B3). They are module-level, not methods on the Document class.

```python
# Add to nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/instrument_pricing_worksheet.py

import frappe
from math import ceil


@frappe.whitelist()
def apply_worksheet_to_contract(worksheet_name, asset, customer_site, start_date=None, end_date=None):
    """
    Create (or update a specified draft) Instrument Placement Contract
    from an Approved Instrument Pricing Worksheet.

    Parameters passed from the frontend dialog:
    - asset: Link to Asset doctype
    - customer_site: Link to Address doctype
    - start_date: optional, defaults to today
    - end_date: optional, defaults to start + contract_years
    """
    ws = frappe.get_doc("Instrument Pricing Worksheet", worksheet_name)

    if ws.status not in ("Approved",):
        frappe.throw(
            frappe._("Worksheet must be Approved before applying to a Contract. Current status: {0}").format(
                ws.status
            )
        )

    naming_series = frappe.db.get_value(
        "DocType", "Instrument Placement Contract", "autoname"
    )

    start = start_date or frappe.utils.today()
    end = end_date or frappe.utils.add_years(start, ws.contract_years or 1)

    # Create the contract
    contract = frappe.get_doc({
        "doctype": "Instrument Placement Contract",
        "naming_series": "NBSIPC-.YYYY./.####",
        "contract_title": ws.name,
        "contract_type": ws.contract_type,
        "customer": ws.customer,
        "customer_site": customer_site,
        "asset": asset,
        "start_date": start,
        "end_date": end,
        "pricing_worksheet": ws.name,
        "total_recovery_target": ws.final_revenue_target,
        "declared_monthly_test_volume": 0,
    })

    from math import ceil

    for line in ws.reagent_costing_lines:
        is_test = line.line_type == "Test Reagent"
        contract.append("contract_lines", {
            "line_type": line.line_type,
            "test_parameter": line.test_parameter,
            "item_code": line.item_code,
            "uom": frappe.db.get_value("Item", line.item_code, "stock_uom"),
            "standard_price": line.cogs_per_pack or line.cogs_per_unit,
            "contract_price": line.selling_price_per_pack if is_test else 0,
            "qty_required_total": line.packs_needed or line.total_units_over_term,
            "min_monthly_qty": ceil(line.monthly_test_volume / line.tests_per_pack) if is_test and line.tests_per_pack else 0,
            "cogs_per_unit": line.cogs_per_pack or line.cogs_per_unit,
        })

    contract.insert(ignore_permissions=True)

    # Create a dedicated Price List for this contract
    price_list = _create_contract_price_list(contract, ws)
    contract.contract_price_list = price_list.name
    contract.save(ignore_permissions=True)

    # Update worksheet status
    ws.status = "Applied to Contract"
    ws.linked_contract = contract.name
    ws.save(ignore_permissions=True)

    return contract.name


def _create_contract_price_list(contract, ws):
    """
    Create a Price List named after the contract with Item Price records
    for each contract line's selling price.

    Follows ERPNext's ``erpnext/stock/doctype/price_list/price_list.py`` pattern.
    """
    pl = frappe.get_doc({
        "doctype": "Price List",
        "price_list_name": f"Contract Pricing - {contract.name}",
        "currency": frappe.db.get_single_value("Global Defaults", "default_currency"),
        "selling": 1,
        "enabled": 1,
        "buying": 0,
    }).insert(ignore_permissions=True)

    for line in ws.reagent_costing_lines:
        if line.line_type == "Test Reagent" and (line.selling_price_per_pack or 0) > 0:
            frappe.get_doc({
                "doctype": "Item Price",
                "price_list": pl.name,
                "item_code": line.item_code,
                "price_list_rate": line.selling_price_per_pack,
                "uom": frappe.db.get_value("Item", line.item_code, "stock_uom"),
                "selling": 1,
                "valid_from": frappe.utils.today(),
            }).insert(ignore_permissions=True)

    return pl
```

---

## 2. Tests

Add to the existing test file created in B3:

```python
# Append to nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/test_instrument_pricing_worksheet.py

import frappe
from frappe.tests.utils import FrappeTestCase
from nbs_customization.nbs_customization.nbs_customization.doctype.instrument_pricing_worksheet.instrument_pricing_worksheet import apply_worksheet_to_contract, calculate_worksheet


class TestApplyWorksheet(FrappeTestCase):
    def setUp(self):
        self.analyzer = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Apply Analyzer", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)

        at = frappe.get_doc(
            {"doctype": "Analyzer Type", "title": "_TST Apply Chem"}
        ).insert(ignore_if_duplicate=True)

        param = frappe.get_doc(
            {"doctype": "Test Parameter", "parameter_name": "_TST Apply Param", "parameter_code": "APLY"}
        ).insert(ignore_if_duplicate=True)

        frappe.get_doc({
            "doctype": "Instrument Specification",
            "item": self.analyzer.item_code,
            "analyzer_type": at.name,
        }).insert()

        self.reagent = frappe.get_doc(
            {"doctype": "Item", "item_code": "_TST Apply Reagent", "item_group": "Products"}
        ).insert(ignore_if_duplicate=True)

        frappe.get_doc({
            "doctype": "Reagent Specification",
            "item": self.reagent.item_code,
            "reagent_role": "Test Reagent",
            "default_cogs_per_pack": 50,
            "default_tests_per_pack": 100,
        }).insert(ignore_if_duplicate=True)

        self.customer = frappe.get_doc({
            "doctype": "Customer", "customer_name": "_TST Apply Customer", "customer_type": "Company"
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

        calculate_worksheet(ws.name)
        ws.reload()
        ws.status = "Approved"
        ws.save()
        self.ws = ws

    def tearDown(self):
        frappe.db.rollback()

    def _setup_asset_and_address(self):
        site = frappe.get_doc({
            "doctype": "Address", "address_title": "_TST Apply Site", "address_type": "Office"
        }).insert(ignore_if_duplicate=True)
        asset = frappe.get_doc({
            "doctype": "Asset", "asset_name": "_TST Apply Asset",
            "item_code": self.analyzer.item_code,
            "company": frappe.db.get_single_value("Global Defaults", "default_company"),
            "gross_purchase_amount": 5000,
            "asset_category": frappe.db.get_value("Asset Category", {}, "name"),
        }).insert(ignore_if_duplicate=True)
        return asset.name, site.name

    def test_contract_created(self):
        asset, site = self._setup_asset_and_address()
        contract_name = apply_worksheet_to_contract(self.ws.name, asset, site)
        contract = frappe.get_doc("Instrument Placement Contract", contract_name)
        self.assertEqual(contract.contract_type, "RRA")
        self.assertEqual(contract.customer, self.customer.name)
        self.assertEqual(contract.total_recovery_target, self.ws.final_revenue_target)

    def test_contract_lines_mapped(self):
        asset, site = self._setup_asset_and_address()
        contract_name = apply_worksheet_to_contract(self.ws.name, asset, site)
        contract = frappe.get_doc("Instrument Placement Contract", contract_name)
        self.assertGreater(len(contract.contract_lines), 0)
        cl = contract.contract_lines[0]
        self.assertEqual(cl.item_code, self.reagent.item_code)

    def test_price_list_created(self):
        asset, site = self._setup_asset_and_address()
        contract_name = apply_worksheet_to_contract(self.ws.name, asset, site)
        contract = frappe.get_doc("Instrument Placement Contract", contract_name)
        self.assertTrue(contract.contract_price_list)

        items = frappe.db.get_all("Item Price", filters={
            "price_list": contract.contract_price_list,
        })
        self.assertGreater(len(items), 0)

    def test_worksheet_status_updated(self):
        asset, site = self._setup_asset_and_address()
        apply_worksheet_to_contract(self.ws.name, asset, site)
        self.ws.reload()
        self.assertEqual(self.ws.status, "Applied to Contract")
        self.assertTrue(self.ws.linked_contract)
```

---

## 3. `hooks.py` registration

No changes needed — the `@frappe.whitelist()` decorator makes the function callable from the client.
