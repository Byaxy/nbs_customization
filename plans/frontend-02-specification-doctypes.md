# F2 — Specification DocTypes Client Scripts

**Depends on:** B1, B2
**Provides:** Client scripts for `Instrument Specification` and `Reagent Specification`

---

## Objective

Add client scripts to the custom specification DocTypes to:
1. Filter `required_reagent` in child grid to only Test Reagent items
2. Prevent duplicate `test_parameter` rows client-side

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_specification/instrument_specification.js` | Modify — add client script |
| `nbs_customization/nbs_customization/nbs_customization/doctype/reagent_specification/reagent_specification.js` | Modify — add client script |

---

## 1. Instrument Specification — `instrument_specification.js`

```javascript
frappe.ui.form.on("Instrument Specification", {
    refresh(frm) {
        _filter_reagent_queries(frm);
    },
});

frappe.ui.form.on("Instrument Test Method", {
    required_reagent(frm, cdt, cdn) {
        // Immediately check if the selected reagent is valid
        const row = locals[cdt][cdn];
        if (!row.required_reagent) return;

        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Reagent Specification",
                filters: { item: row.required_reagent },
                fieldname: "reagent_role",
            },
            callback(r) {
                if (r.message && r.message.reagent_role !== "Test Reagent") {
                    frappe.msgprint({
                        title: __("Invalid Reagent"),
                        message: __(
                            "Item {0} has Reagent Role '{1}'. Only Test Reagent items are allowed.",
                            [row.required_reagent, r.message.reagent_role]
                        ),
                        indicator: "red",
                    });
                    frappe.model.set_value(cdt, cdn, "required_reagent", null);
                }
            },
        });
    },

    test_parameter(frm, cdt, cdn) {
        _check_duplicate_parameter(frm, cdt, cdn);
    },
});

function _filter_reagent_queries(frm) {
    frm.set_query("required_reagent", "supported_test_methods", () => ({
        query: "nbs_customization.controllers.placement.valid_items.get_reagent_items_query",
        filters: { reagent_role: "Test Reagent" },
    }));
}

function _check_duplicate_parameter(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.test_parameter) return;

    const child_table = frm.doc.supported_test_methods || [];
    const count = child_table.filter(
        (r) => r.test_parameter === row.test_parameter && r.name !== row.name
    ).length;

    if (count > 0) {
        frappe.msgprint({
            title: __("Duplicate Parameter"),
            message: __("Test Parameter {0} is already in the list.", [row.test_parameter]),
            indicator: "orange",
        });
        frappe.model.set_value(cdt, cdn, "test_parameter", null);
    }
}
```

---

## 2. Reagent Specification — `reagent_specification.js`

```javascript
frappe.ui.form.on("Reagent Specification", {
    refresh(frm) {
        _toggle_sections(frm);
    },

    reagent_role(frm) {
        _toggle_sections(frm);
    },
});

function _toggle_sections(frm) {
    // The sections are already gated by depends_on in the schema,
    // but this ensures field descriptions/placeholders adjust accordingly.
    const is_reagent = frm.doc.reagent_role === "Test Reagent";
    const is_consumable = frm.doc.reagent_role === "Non-Test Consumable";

    if (is_reagent) {
        frm.set_df_property("test_panel_group", "reqd", 1);
    } else {
        frm.set_df_property("test_panel_group", "reqd", 0);
    }
}
```

---

## 3. Verification

- In Instrument Specification's child grid, the `required_reagent` picker only shows Items with Reagent Role = "Test Reagent".
- Adding a duplicate test parameter warns the user immediately.
- Reagent Specification's sections toggle cleanly on role change.
