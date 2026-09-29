# F9 — Contract Amendment Client Script

**Depends on:** B10 (scheduled amendment processing), B5 (contract lifecycle)
**Provides:** Client script for `Contract Amendment`

---

## Objective

Custom buttons:
- **"Approve"** — moves amendment to `Approved` status
- **"Mark Effective"** — only enabled on or after `effective_date`, triggers the §4.3 db_set pushback to the Contract

---

## Files to modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/contract_amendment/contract_amendment.js` | Create — client script |

---

## Client script — `contract_amendment.js`

```javascript
frappe.ui.form.on("Contract Amendment", {
    refresh(frm) {
        _add_approve_button(frm);
        _add_mark_effective_button(frm);
    },
});

function _add_approve_button(frm) {
    if (frm.doc.status !== "Pending Customer Signature") return;

    frm.add_custom_button(__("Approve Amendment"), () => {
        frappe.confirm(
            __("Are you sure you want to approve this amendment? The new terms will take effect on {0}.",
                [frm.doc.effective_date]),
            () => {
                frm.set_value("status", "Approved");
                frm.set_value("approved_by", frappe.session.user);
                frm.save();
            }
        );
    }, __("Actions"));
}

function _add_mark_effective_button(frm) {
    if (frm.doc.status !== "Approved") return;

    const today = frappe.datetime.get_today();
    const effective = frm.doc.effective_date;
    const is_eligible = effective && effective <= today;

    frm.add_custom_button(__("Mark Effective"), () => {
        frappe.call({
            method: "nbs_customization.controllers.placement.amendment.mark_effective",
            args: { amendment_name: frm.doc.name },
            freeze: true,
            freeze_message: __("Applying amendment to contract..."),
            callback(r) {
                if (r.message) {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Amendment is now effective. Contract terms updated."),
                        indicator: "green",
                    });
                }
            },
        });
    }, __("Actions"));

    // Disable if before effective date
    if (!is_eligible) {
        frm.set_df_property("_mark_effective_btn", "disabled", true);
        // Tooltip explaining why
        frm.set_df_property("_mark_effective_btn", "label",
            effective
                ? __("Mark Effective (available after {0})", [effective])
                : __("Mark Effective (requires an effective date)"));
    }
}
```

---

## Backend helper — `amendment.py` (new)

Add a small whitelisted method called by the button:

```python
# nbs_customization/controllers/placement/amendment.py

import frappe


@frappe.whitelist()
def mark_effective(amendment_name):
    """
    Manual trigger to mark an amendment as Effective and push new
    terms back to the Contract. The daily scheduler (B10) also does
    this automatically — this provides a manual path for backfill/testing.
    """
    doc = frappe.get_doc("Contract Amendment", amendment_name)

    if doc.status != "Approved":
        frappe.throw(
            frappe._("Amendment must be Approved before it can be marked Effective.")
        )

    if doc.effective_date > frappe.utils.today():
        frappe.throw(
            frappe._("Cannot mark amendment Effective before its effective date ({0}).").format(
                doc.effective_date
            )
        )

    from nbs_customization.tasks import _apply_amendment_to_contract
    _apply_amendment_to_contract(doc)

    doc.status = "Effective"
    doc.db_set("status", "Effective")

    return doc.name
```

Move the amendment-to-contract push logic from the scheduled job into a shared `_apply_amendment_to_contract` function so it's callable from both the scheduler and the manual button.

---

## Verification

- **"Approve Amendment"** only visible when status is `Pending Customer Signature`.
- **"Mark Effective"** only visible when status is `Approved`.
- It's disabled until `effective_date <= today`.
- After clicking, the Contract's fields update immediately.
