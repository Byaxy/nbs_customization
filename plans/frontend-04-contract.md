# F4 — Instrument Placement Contract Client Script

**Depends on:** B2, B4, B5 (backend methods exist)
**Provides:** Client script for the custom `Instrument Placement Contract` DocType

---

## Objective

Full client script with:
1. `customer_site` filtered to Addresses linked to the selected Customer
2. `asset` filtered to available Assets (status Warehouse), or the currently linked one
3. `contract_lines.item_code` filtered per analyzer (B2)
4. **"Create Analyzer Deployment"** button
5. Recovery progress indicator
6. **"Retrieve Analyzer"** shortcut button

---

## Files to create/modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_placement_contract/instrument_placement_contract.js` | Modify — add full client script |

---

## Client script — `instrument_placement_contract.js`

```javascript
frappe.ui.form.on("Instrument Placement Contract", {
    refresh(frm) {
        _setup_queries(frm);
        _add_deployment_button(frm);
        _add_retrieve_button(frm);
        _show_recovery_progress(frm);
        _show_dashboard_alert(frm);
    },

    asset(frm) {
        _fetch_serial_no(frm);
    },

    start_date(frm) {
        _compute_duration(frm);
    },

    end_date(frm) {
        _compute_duration(frm);
    },
});

frappe.ui.form.on("Contract Reagent Line", {
    item_code(frm, cdt, cdn) {
        _fetch_line_details(frm, cdt, cdn);
    },
});

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

function _setup_queries(frm) {
    // Customer site filtered to the selected customer
    frm.set_query("customer_site", () => ({
        filters: {
            link_doctype: "Customer",
            link_name: frm.doc.customer,
        },
    }));

    // Asset: available (Warehouse) OR the one already linked to this contract
    frm.set_query("asset", () => {
        const filters = {
            custom_current_deployment_status: "Warehouse",
        };
        if (frm.doc.asset) {
            // Also allow the already-linked asset
            filters.name = ["in", [frm.doc.asset]];
        }
        return { filters };
    });

    // Contract lines scoped to analyzer
    frm.set_query("item_code", "contract_lines", () => ({
        query: "nbs_customization.controllers.placement.valid_items.get_valid_reagent_items_query",
        filters: { analyzer_item: frm.doc.analyzer_pid },
    }));
}

function _fetch_serial_no(frm) {
    if (!frm.doc.asset) return;
    frappe.db.get_value("Asset", frm.doc.asset, "serial_no", (r) => {
        if (r && r.serial_no) {
            frm.set_value("serial_no", r.serial_no);
        }
    });
}

function _compute_duration(frm) {
    if (frm.doc.start_date && frm.doc.end_date) {
        const start = frappe.datetime.str_to_obj(frm.doc.start_date);
        const end = frappe.datetime.str_to_obj(frm.doc.end_date);
        const months = (end.getFullYear() - start.getFullYear()) * 12
            + (end.getMonth() - start.getMonth());
        frm.set_value("contract_duration_months", Math.max(months, 0));
    }
}

function _fetch_line_details(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.item_code) return;

    frappe.call({
        method: "frappe.client.get_value",
        args: {
            doctype: "Reagent Specification",
            filters: { item: row.item_code },
            fieldname: ["reagent_role", "default_cogs_per_pack", "default_cogs_per_unit"],
        },
        callback(r) {
            if (!r.message) return;
            const spec = r.message;
            frappe.model.set_value(cdt, cdn, "cogs_per_unit",
                spec.default_cogs_per_pack || spec.default_cogs_per_unit);
        },
    });
}

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------

function _add_deployment_button(frm) {
    if (frm.doc.contract_status !== "Active") return;
    if (frm.doc.__islocal) return;

    // Check if deployment already exists
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Analyzer Deployment",
            filters: { contract: frm.doc.name, docstatus: ["<", 2] },
            fields: ["name"],
            limit: 1,
        },
        callback(r) {
            if (r.message && r.message.length) {
                // Already has one — show "View"
                frm.add_custom_button(__("Analyzer Deployment"), () => {
                    frappe.set_route("Form", "Analyzer Deployment", r.message[0].name);
                }, __("View"));
            } else {
                frm.add_custom_button(__("Analyzer Deployment"), () => {
                    frappe.model.open_mapped_doc({
                        method: "nbs_customization.controllers.placement.contract.make_deployment",
                        frm: frm,
                    });
                }, __("Create"));
            }
        },
    });
}

function _add_retrieve_button(frm) {
    if (frm.doc.contract_status !== "Active") return;

    frm.add_custom_button(__("Retrieve Analyzer"), () => {
        // Open a new Repossession Request pre-filled
        frappe.model.open_mapped_doc({
            method: "nbs_customization.controllers.placement.contract.make_repossession_request",
            frm: frm,
        });
    }, __("Actions"));
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

function _show_recovery_progress(frm) {
    if (!frm.doc.total_recovery_target) return;

    const pct = frm.doc.recovery_pct_collected || 0;
    const color = pct >= 100 ? "green" : pct >= 75 ? "orange" : "red";

    frm.dashboard.add_progress(__("Recovery Progress (Collected)"), pct, color);
}

function _show_dashboard_alert(frm) {
    if (!frm.doc.custom_instrument_placement_contract) return;

    const contract_link = frappe.utils.get_form_link(
        "Instrument Placement Contract",
        frm.doc.custom_instrument_placement_contract,
        true
    );
    frm.dashboard.add_comment(
        __("Linked to Placement Contract: {0} — {1}",
            [contract_link, frm.doc.custom_instrument_placement_contract])
    );
}
```

---

## Verification

- `customer_site` shows only Addresses linked to the selected Customer.
- `asset` shows only Warehouse-status Assets (or the current one).
- `contract_lines.item_code` filtered to valid items per `analyzer_pid`.
- Recovery progress bar visible when a target exists.
- Buttons visible/invisible based on `contract_status`.
