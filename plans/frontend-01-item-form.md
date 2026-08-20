# F1 — Item Form Client Script

**Depends on:** B1, B2 (backend specs + query helpers exist)
**Provides:** Client-side enhancements to the native Item DocType for placement fields

---

## Objective

Add a client script to the native Item DocType that:
1. Filters `instrument_specification` / `reagent_specification` link queries to show only records not already linked to a different Item
2. Shows inline hints guiding the user which field to fill based on context

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/public/js/item.js` | **Create** — Item client script (new file for native Item DocType) |
| `nbs_customization/hooks.py` | Modify — add `doctype_js` entry for Item |

---

## 1. Client script — `item.js`

```javascript
// nbs_customization/public/js/item.js

frappe.ui.form.on("Item", {
    refresh(frm) {
        _setup_placement_fields(frm);
    },

    is_placement_item(frm) {
        _toggle_placement_fields(frm);
    },
});

function _setup_placement_fields(frm) {
    _toggle_placement_fields(frm);

    // Filter instrument_specification: only show specs not linked to another item
    frm.set_query("instrument_specification", () => ({
        filters: {
            item: ["in", [frm.doc.name, ""]],  // current item or unlinked
        },
    }));

    // Filter reagent_specification: same pattern
    frm.set_query("reagent_specification", () => ({
        filters: {
            item: ["in", [frm.doc.name, ""]],
        },
    }));
}

function _toggle_placement_fields(frm) {
    const show = frm.doc.is_placement_item === 1;

    // The two link fields are already gated by depends_on in the schema,
    // but add an inline hint below each.
    if (show) {
        frm.set_df_property("instrument_specification", "description",
            __("Select the Instrument Specification that defines this analyzer's supported tests and consumables.")
        );
        frm.set_df_property("reagent_specification", "description",
            __("Select the Reagent Specification if this is a reagent or consumable item.")
        );
    }
}
```

---

## 2. `hooks.py` update

```python
doctype_js = {
    "Sales Order": "public/js/sales_order.js",
    "Delivery Note": "public/js/delivery_note.js",
    "Landed Cost Voucher": "public/js/landed_cost_voucher.js",
    "Purchase Receipt": "public/js/purchase_receipt.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Batch": "public/js/batch.js",
    "Payment Entry": "public/js/payment_entry.js",
    "Item": "public/js/item.js",  # <-- new
}
```

---

## 3. Verification

- Check the Item form shows the "Placement Program" collapsible section after `item_group`.
- With `is_placement_item` checked, both Link fields appear with descriptive hints.
- The `instrument_specification` picker only shows records where `item` matches the current Item or is empty.
- `bench build` after JS changes.
