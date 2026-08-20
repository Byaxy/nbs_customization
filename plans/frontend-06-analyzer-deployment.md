# F6 — Analyzer Deployment Client Script

**Depends on:** B7 (deployment side effects backend)
**Provides:** Client script for `Analyzer Deployment` with guided status transition buttons

---

## Objective

Custom buttons for each `deployment_status` transition, each simply setting the field and saving (side effects fire server-side in `validate` per B7). Filter `asset_location` to customer-site Locations.

---

## Files to modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/analyzer_deployment/analyzer_deployment.js` | Modify — add full client script |

---

## Client script — `analyzer_deployment.js`

```javascript
frappe.ui.form.on("Analyzer Deployment", {
    refresh(frm) {
        _setup_queries(frm);
        _add_status_buttons(frm);
    },
});

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

function _setup_queries(frm) {
    // asset_location: filter to customer-site Locations
    frm.set_query("asset_location", () => ({
        filters: {
            is_group: 0,
        },
    }));
}

// ---------------------------------------------------------------------------
// Status transition buttons
// ---------------------------------------------------------------------------

function _add_status_buttons(frm) {
    if (frm.doc.__islocal) return;

    const status = frm.doc.deployment_status;

    if (status === "Deployed") {
        frm.add_custom_button(__("Send for Service"), () => {
            _transition_to(frm, "Under Service");
        }, __("Status"));

        frm.add_custom_button(__("Retrieve Analyzer"), () => {
            _show_retrieval_dialog(frm, "Temporarily Retrieved");
        }, __("Status"));
    }

    if (status === "Under Service") {
        frm.add_custom_button(__("Return from Service"), () => {
            _transition_to(frm, "Deployed");
        }, __("Status"));
    }

    if (status === "Temporarily Retrieved") {
        frm.add_custom_button(__("Deploy Again"), () => {
            _transition_to(frm, "Deployed");
        }, __("Status"));

        frm.add_custom_button(__("Permanently Retrieve"), () => {
            _show_retrieval_dialog(frm, "Permanently Retrieved");
        }, __("Status"));
    }

    // "Permamently Retrieved" is terminal — no status buttons
}

function _transition_to(frm, new_status) {
    frm.set_value("deployment_status", new_status);
    frm.save();
}

function _show_retrieval_dialog(frm, new_status) {
    const dialog = new frappe.ui.Dialog({
        title: __("Analyzer Retrieval — {0}", [new_status === "Permanently Retrieved"
            ? __("Permanent") : __("Temporary")]),
        fields: [
            {
                fieldname: "retrieval_reason",
                label: __("Retrieval Reason"),
                fieldtype: "Select",
                options: [
                    "Contract Breach",
                    "Contract Fulfilled",
                    "Ownership Transfer",
                    "Analyzer Service",
                    "Analyzer Upgrade",
                    "Customer Request",
                    "Contract Expiry",
                    "Other",
                ],
                reqd: 1,
            },
            {
                fieldname: "condition_at_return",
                label: __("Analyzer Condition at Return"),
                fieldtype: "Select",
                options: ["", "Good", "Damaged", "Needs Repair"],
            },
            {
                fieldname: "retrieval_date",
                label: __("Retrieval Date"),
                fieldtype: "Date",
                default: frappe.datetime.get_today(),
            },
        ],
        primary_action_label: __("Confirm Retrieval"),
        primary_action(values) {
            frm.set_value("retrieval_reason", values.retrieval_reason);
            frm.set_value("condition_at_return", values.condition_at_return || null);
            frm.set_value("retrieval_date", values.retrieval_date);
            frm.set_value("deployment_status", new_status);
            frm.save();
            dialog.hide();
        },
    });
    dialog.show();
}
```

---

## Verification

- Buttons only appear for valid transitions from the current status.
- **"Retrieve Analyzer"** prompts for reason, condition, and date before saving.
- `asset_location` filter shows only non-group Locations.
