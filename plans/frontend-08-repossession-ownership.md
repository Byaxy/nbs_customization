# F8 — Repossession Request / Ownership Transfer Request Client Scripts

**Depends on:** B11, B12 (backend methods exist)
**Provides:** Client scripts for both high-stakes documents

---

## Objective

Client scripts with:
1. **Repossession Request** — "Approve", "Execute Retrieval", "Close" buttons gated on status
2. **Ownership Transfer Request** — "Send for Finance Review", "Send for Legal Review", "Complete Transfer" buttons with confirmation dialogs

---

## Files to modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/repossession_request/repossession_request.js` | Create — client script |
| `nbs_customization/nbs_customization/nbs_customization/doctype/ownership_transfer_request/ownership_transfer_request.js` | Create — client script |

---

## 1. Repossession Request — `repossession_request.js`

```javascript
frappe.ui.form.on("Repossession Request", {
    refresh(frm) {
        _add_status_buttons(frm);
    },
});

function _add_status_buttons(frm) {
    const status = frm.doc.status;

    if (status === "Draft") {
        frm.add_custom_button(__("Submit for Approval"), () => {
            frm.save("submit");
        });
    }

    if (status === "Pending Approval") {
        frm.add_custom_button(__("Approve"), () => {
            frappe.confirm(
                __("Are you sure you want to approve this repossession request? This authorizes the physical retrieval of the analyzer."),
                () => {
                    frm.set_value("status", "Approved");
                    frm.set_value("approved_by", frappe.session.user);
                    frm.set_value("approval_date", frappe.datetime.get_today());
                    frm.save();
                }
            );
        }, __("Actions"));

        frm.add_custom_button(__("Reject"), () => {
            frm.set_value("status", "Closed");
            frm.save();
        }, __("Actions"));
    }

    if (status === "Approved") {
        frm.add_custom_button(__("Execute Retrieval"), () => {
            frappe.confirm(
                __("This will execute the analyzer retrieval. The Analyzer Deployment will be updated to 'Permanently Retrieved'. Continue?"),
                () => {
                    frappe.call({
                        method: "nbs_customization.nbs_customization.nbs_customization.doctype.repossession_request.repossession_request.execute_retrieval",
                        args: { repossession_request_name: frm.doc.name },
                        freeze: true,
                        freeze_message: __("Executing retrieval..."),
                        callback(r) {
                            if (r.message) {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __("Retrieval completed. Deployment: {0}", [r.message]),
                                    indicator: "green",
                                });
                            }
                        },
                    });
                }
            );
        }, __("Actions"));
    }
}
```

---

## 2. Ownership Transfer Request — `ownership_transfer_request.js`

```javascript
frappe.ui.form.on("Ownership Transfer Request", {
    refresh(frm) {
        _add_status_buttons(frm);
    },
});

function _add_status_buttons(frm) {
    const status = frm.doc.status;

    if (status === "Draft") {
        frm.add_custom_button(__("Submit"), () => {
            frm.save("submit");
        });
    }

    if (status === "Pending Finance Review") {
        frm.add_custom_button(__("Approve (Finance)"), () => {
            frappe.confirm(
                __("Confirm finance review approval?"),
                () => {
                    frm.set_value("finance_reviewed_by", frappe.session.user);
                    frm.set_value("finance_review_date", frappe.datetime.get_today());
                    frm.set_value("status", "Pending Legal Review");
                    frm.save();
                }
            );
        }, __("Approvals"));
    }

    if (status === "Pending Legal Review") {
        frm.add_custom_button(__("Approve (Legal)"), () => {
            frappe.confirm(
                __("Confirm legal review approval?"),
                () => {
                    frm.set_value("legal_reviewed_by", frappe.session.user);
                    frm.set_value("legal_review_date", frappe.datetime.get_today());
                    frm.set_value("status", "Approved");
                    frm.save();
                }
            );
        }, __("Approvals"));
    }

    if (status === "Approved") {
        // Gate on transfer certificate
        frm.add_custom_button(__("Complete Transfer"), () => {
            if (!frm.doc.transfer_certificate) {
                frappe.msgprint(__("Transfer Certificate must be attached before completing the transfer."));
                return;
            }

            frappe.confirm(
                __(
                    "⚠️ This action is irreversible.\n\n"
                    + "Completing the transfer will:\n"
                    + "- Permanently remove this analyzer from the company's asset books\n"
                    + "- Mark the contract as Fulfilled\n"
                    + "- Transfer ownership to the customer\n\n"
                    + "Continue?"
                ),
                () => {
                    frappe.call({
                        method: "nbs_customization.nbs_customization.nbs_customization.doctype.ownership_transfer_request.ownership_transfer_request.complete_transfer",
                        args: { otr_name: frm.doc.name },
                        freeze: true,
                        freeze_message: __("Completing transfer..."),
                        callback(r) {
                            if (r.message) {
                                frm.reload_doc();
                                frappe.show_alert({
                                    message: __("Transfer completed successfully."),
                                    indicator: "green",
                                });
                            }
                        },
                    });
                }
            );
        }, __("Actions"));
    }
}
```

---

## Verification

- **Repossession Request**: buttons appear/disappear per status. Execute Retrieval requires Approved status and shows confirmation.
- **Ownership Transfer Request**: dual-approval flow (Finance → Legal → Approved). Complete Transfer requires certificate attachment and shows a clear irreversible-action warning.
