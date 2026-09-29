# F3 — Instrument Pricing Worksheet Client Script

**Depends on:** B2, B3 (backend methods exist)
**Provides:** Client script for the custom `Instrument Pricing Worksheet` DocType

---

## Objective

Full client script with:
1. `analyzer_pid` filtered to placement Items with an Instrument Specification
2. Child grid `item_code` filtered per the selected analyzer (calls B2)
3. Dynamic re-filtering when analyzer changes
4. **"Calculate"** button calling B3's `calculate_worksheet_wrapper`
5. **"Apply to Contract"** button calling B4's `apply_worksheet_to_contract`
6. Auto-set `calculation_output_type` default based on `contract_type`

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_pricing_worksheet/instrument_pricing_worksheet.js` | Modify — add full client script |

---

## Client script — `instrument_pricing_worksheet.js`

```javascript
frappe.ui.form.on("Instrument Pricing Worksheet", {
    refresh(frm) {
        _setup_queries(frm);
        _add_calculate_button(frm);
        _add_apply_button(frm);
    },

    analyzer_pid(frm) {
        _update_analyzer_type(frm);
        _refresh_reagent_queries(frm);
        _warn_existing_lines(frm);
    },

    contract_type(frm) {
        _auto_set_calculation_output(frm);
    },
});

// Child table events
frappe.ui.form.on("Reagent Costing Line", {
    item_code(frm, cdt, cdn) {
        _fetch_reagent_details(frm, cdt, cdn);
    },
    monthly_test_volume(frm, cdt, cdn) {
        _update_total_tests(frm, cdt, cdn);
    },
});

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

function _setup_queries(frm) {
    // analyzer_pid: only Items with is_placement_item = 1 + Instrument Specification
    frm.set_query("analyzer_pid", () => ({
        filters: {
            is_placement_item: 1,
            instrument_specification: ["!=", ""],
        },
    }));

    _refresh_reagent_queries(frm);
}

function _refresh_reagent_queries(frm) {
    if (!frm.doc.analyzer_pid) return;

    frm.set_query("item_code", "reagent_costing_lines", () => ({
        query: "nbs_customization.controllers.placement.valid_items.get_valid_reagent_items_query",
        filters: { analyzer_item: frm.doc.analyzer_pid },
    }));
}

// ---------------------------------------------------------------------------
// Field change handlers
// ---------------------------------------------------------------------------

function _update_analyzer_type(frm) {
    if (!frm.doc.analyzer_pid) return;

    frappe.call({
        method: "frappe.client.get_value",
        args: {
            doctype: "Instrument Specification",
            filters: { item: frm.doc.analyzer_pid },
            fieldname: "analyzer_type",
        },
        callback(r) {
            if (r.message) {
                frm.set_value("analyzer_type", r.message.analyzer_type);
            }
        },
    });
}

function _warn_existing_lines(frm) {
    const old = frm.doc.analyzer_pid;
    if (!old) return;

    const lines = frm.doc.reagent_costing_lines || [];
    if (lines.length > 0) {
        frappe.show_alert({
            message: __(
                "Analyzer changed. Please verify that existing costing lines are still valid."
            ),
            indicator: "orange",
        });
    }
}

function _auto_set_calculation_output(frm) {
    if (frm.doc.contract_type === "CPT") {
        frm.set_value("calculation_output_type", "Revenue Share Percentage");
    } else if (["RRA", "RLO"].includes(frm.doc.contract_type)) {
        frm.set_value("calculation_output_type", "Markup Factor on Reagent Price");
    }
}

// ---------------------------------------------------------------------------
// Button handlers
// ---------------------------------------------------------------------------

function _add_calculate_button(frm) {
    frm.add_custom_button(__("Calculate"), () => {
        frappe.call({
            method: "nbs_customization.nbs_customization.nbs_customization.doctype.instrument_pricing_worksheet.instrument_pricing_worksheet.calculate_worksheet_wrapper",
            args: { worksheet_name: frm.doc.name },
            freeze: true,
            freeze_message: __("Calculating pricing..."),
            callback(r) {
                frm.reload_doc();
                frappe.show_alert({
                    message: __("Worksheet calculated successfully."),
                    indicator: "green",
                });
            },
        });
    });
}

function _add_apply_button(frm) {
    frm.add_custom_button(__("Apply to Contract"), () => {
        frappe.call({
            method: "nbs_customization.nbs_customization.nbs_customization.doctype.instrument_pricing_worksheet.instrument_pricing_worksheet.apply_worksheet_to_contract",
            args: { worksheet_name: frm.doc.name },
            freeze: true,
            freeze_message: __("Creating contract..."),
            callback(r) {
                if (r.message) {
                    frappe.set_route("Form", "Instrument Placement Contract", r.message);
                }
            },
        });
    });

    // Show/hide based on status
    frm.set_df_property("_apply_button", "hidden", frm.doc.status !== "Approved");
}

// ---------------------------------------------------------------------------
// Child row helpers
// ---------------------------------------------------------------------------

function _fetch_reagent_details(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.item_code) return;

    frappe.call({
        method: "frappe.client.get_value",
        args: {
            doctype: "Reagent Specification",
            filters: { item: row.item_code },
            fieldname: [
                "reagent_role", "default_pack_volume_ml", "default_tests_per_pack",
                "default_cogs_per_pack", "default_consumption_qty",
                "default_consumption_frequency", "default_cogs_per_unit",
            ],
        },
        callback(r) {
            if (!r.message) return;
            const spec = r.message;
            frappe.model.set_value(cdt, cdn, "line_type",
                spec.reagent_role || "Test Reagent");
            if (spec.reagent_role === "Test Reagent") {
                frappe.model.set_value(cdt, cdn, "pack_volume_ml", spec.default_pack_volume_ml);
                frappe.model.set_value(cdt, cdn, "tests_per_pack", spec.default_tests_per_pack);
                frappe.model.set_value(cdt, cdn, "cogs_per_pack", spec.default_cogs_per_pack);
            } else {
                frappe.model.set_value(cdt, cdn, "consumption_qty", spec.default_consumption_qty);
                frappe.model.set_value(cdt, cdn, "consumption_frequency", spec.default_consumption_frequency);
                frappe.model.set_value(cdt, cdn, "cogs_per_unit", spec.default_cogs_per_unit);
            }
        },
    });
}

function _update_total_tests(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.monthly_test_volume && frm.doc.contract_years) {
        const total = row.monthly_test_volume * 12 * frm.doc.contract_years;
        frappe.model.set_value(cdt, cdn, "total_tests_over_term", total);
    }
}
```

---

## Verification

- Filter `analyzer_pid` only shows placement Items with a Specification.
- Changing `analyzer_pid` re-filters the `item_code` in the child grid.
- **"Calculate"** button calls the backend and refreshes the form.
- **"Apply to Contract"** visible only when status is Approved.
- `calculation_output_type` auto-sets when `contract_type` changes.
