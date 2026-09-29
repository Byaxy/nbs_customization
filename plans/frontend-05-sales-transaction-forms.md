# F5 — Sales Order / Delivery Note / Sales Invoice Client Scripts

**Depends on:** B2 (query helpers), B6 (backend hooks exist)
**Provides:** Placement enhancements to existing native DocType JS files

---

## Objective

Append into the **existing** `sales_order.js`, `delivery_note.js`, `sales_invoice.js` files (new JS appended to end of each file, must not override existing functions):

1. When `custom_instrument_placement_contract` is set:
   - Auto-apply the contract's price list to the transaction
   - Filter every item row's query to the contract's valid reagent/consumable list
   - Show a persistent dashboard indicator
2. Validate that contract-linked and standard-sale items are not mixed (already server-enforced in B6, but show a client-side warning too)

---

## Files to modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/public/js/sales_order.js` | Append placement code |
| `nbs_customization/nbs_customization/public/js/delivery_note.js` | Append placement code |
| `nbs_customization/nbs_customization/public/js/sales_invoice.js` | Append placement code |

---

## 1. Shared placement logic (appended to each file)

The code below is structurally identical for all three DocTypes. Use a shared helper pattern:

```javascript
// === PLACEMENT CONTRACT SUPPORT ===
// Appended to existing sales_order.js / delivery_note.js / sales_invoice.js

frappe.ui.form.on("Sales Order", {  // Change doctype name per file
    refresh(frm) {
        _setup_placement_contract(frm);
    },

    custom_instrument_placement_contract(frm) {
        _on_contract_change(frm);
    },
});

// Child table — item_code filter
frappe.ui.form.on("Sales Order Item", {  // Change child doctype per file
    item_code(frm, cdt, cdn) {
        _on_item_change(frm, cdt, cdn);
    },
});

// -----------------------

let _contract_data_cache = {};

function _setup_placement_contract(frm) {
    _refresh_contract_indicator(frm);
    _setup_item_query(frm);
}

function _on_contract_change(frm) {
    const contract_name = frm.doc.custom_instrument_placement_contract;

    if (!contract_name) {
        _contract_data_cache = {};
        frm.set_value("selling_price_list", null);
        _refresh_contract_indicator(frm);
        return;
    }

    // Fetch contract details
    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Instrument Placement Contract",
            name: contract_name,
        },
        callback(r) {
            if (!r.message) return;
            const contract = r.message;
            _contract_data_cache = contract;

            // Auto-set price list
            if (contract.contract_price_list) {
                frm.set_value("selling_price_list", contract.contract_price_list);
                // Trigger price recalculation
                frm.trigger("selling_price_list");
            }

            _setup_item_query(frm);
            _refresh_contract_indicator(frm);
        },
    });
}

function _setup_item_query(frm) {
    const contract = frm.doc.custom_instrument_placement_contract;
    if (!contract) return;

    // Determine child table and item field
    const child_table = _get_child_table(frm);
    const item_field = _get_item_field(frm);

    frm.set_query(item_field, child_table, () => ({
        query: "nbs_customization.controllers.placement.valid_items.get_valid_reagent_items_query",
        filters: { contract_name: contract },
    }));
}

function _on_item_change(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.item_code || !frm.doc.custom_instrument_placement_contract) return;

    // Fetch contract price from the contract's price list
    const contract = _contract_data_cache;
    if (contract && contract.contract_price_list) {
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Item Price",
                filters: {
                    item_code: row.item_code,
                    price_list: contract.contract_price_list,
                    selling: 1,
                },
                fieldname: "price_list_rate",
            },
            callback(r) {
                if (r.message && r.message.price_list_rate) {
                    frappe.model.set_value(cdt, cdn, "rate", r.message.price_list_rate);
                }
            },
        });
    }

    // Fetch description
    frappe.db.get_value("Item", row.item_code, "description", (r) => {
        if (r && r.description) {
            frappe.model.set_value(cdt, cdn, "description", r.description);
        }
    });
}

function _refresh_contract_indicator(frm) {
    const contract = frm.doc.custom_instrument_placement_contract;
    if (!contract) return;

    // Show indicator on the form
    const contract_type = _contract_data_cache?.contract_type || "";
    const indicator_color = contract_type === "CPT" ? "blue" : "green";
    frm.dashboard.add_comment(
        `<span class="indicator ${indicator_color}">
            ${__("Linked to Placement Contract: {0} — {1}", [contract, contract_type])}
        </span>`
    );
}

// ----- DocType-specific helpers -----

function _get_child_table(frm) {
    const map = {
        "Sales Order": "items",
        "Delivery Note": "items",
        "Sales Invoice": "items",
    };
    return map[frm.doctype] || "items";
}

function _get_item_field(frm) {
    // Most use "item_code" directly
    return "item_code";
}
```

---

## 2. Implementation per file

### `sales_order.js`
- Append all the code above with `frappe.ui.form.on("Sales Order", ...)` and `frappe.ui.form.on("Sales Order Item", ...)`
- Keep existing functions (loan waybill conversion logic)

### `delivery_note.js`
- Same but with `"Delivery Note"` and `"Delivery Note Item"`
- Note: Delivery Note already has existing `before_save`, `validate`, etc. in `hooks.py` — the client script is independent

### `sales_invoice.js`
- Same with `"Sales Invoice"` and `"Sales Invoice Item"`
- Existing `sales_invoice.js` is very small (just a `refresh` that removes a button) — append after it

---

## Verification

- Open Sales Order → set `custom_instrument_placement_contract` → price list auto-fills → items filtered.
- Dashboard shows contract link indicator.
- Adding an invalid item shows a warning (server validation also catches it on save).
- Existing functionality (loan waybill buttons on SO) still works.
