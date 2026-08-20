# F7 — Monthly Reconciliation / Revenue Share Statement Client Scripts

**Depends on:** B8, B9 (backend generation methods)
**Provides:** Client scripts for both period-end documents

---

## Objective

Client scripts for:
1. **Monthly Reconciliation** — "Generate for Period" button, "Create Shortfall Penalty Invoice" button
2. **Revenue Share Statement** — "Generate for Period" button

---

## Files to modify

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/monthly_reconciliation/monthly_reconciliation.js` | Create — client script |
| `nbs_customization/nbs_customization/nbs_customization/doctype/revenue_share_statement/revenue_share_statement.js` | Create — client script |

---

## 1. Monthly Reconciliation — `monthly_reconciliation.js`

```javascript
frappe.ui.form.on("Monthly Reconciliation", {
    refresh(frm) {
        _add_generate_button(frm);
        _add_penalty_button(frm);
    },
});

function _add_generate_button(frm) {
    frm.add_custom_button(__("Generate for Period"), () => {
        if (!frm.doc.contract || !frm.doc.period) {
            frappe.msgprint(__("Please select a Contract and Period first."));
            return;
        }

        frappe.call({
            method: "nbs_customization.nbs_customization.nbs_customization.doctype.monthly_reconciliation.monthly_reconciliation.generate_monthly_reconciliation",
            args: {
                contract_name: frm.doc.contract,
                period: frm.doc.period,
            },
            freeze: true,
            freeze_message: __("Generating reconciliation..."),
            callback(r) {
                if (r.message) {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Reconciliation generated: {0}", [r.message]),
                        indicator: "green",
                    });
                }
            },
        });
    });
}

function _add_penalty_button(frm) {
    if (frm.doc.compliance_status !== "Breach") return;

    frm.add_custom_button(__("Create Shortfall Penalty Invoice"), () => {
        frappe.call({
            method: "nbs_customization.nbs_customization.nbs_customization.doctype.monthly_reconciliation.monthly_reconciliation.create_penalty_invoice",
            args: { reconciliation_name: frm.doc.name },
            freeze: true,
            callback(r) {
                if (r.message) {
                    frm.set_value("penalty_invoice", r.message);
                    frm.save();
                    frappe.show_alert({
                        message: __("Penalty Invoice {0} created.", [r.message]),
                        indicator: "green",
                    });
                }
            },
        });
    }, __("Actions"));
}
```

---

## 2. Revenue Share Statement — `revenue_share_statement.js`

```javascript
frappe.ui.form.on("Revenue Share Statement", {
    refresh(frm) {
        _add_generate_button(frm);
    },
});

function _add_generate_button(frm) {
    frm.add_custom_button(__("Generate for Period"), () => {
        if (!frm.doc.contract || !frm.doc.period) {
            frappe.msgprint(__("Please select a Contract and Period first."));
            return;
        }

        frappe.call({
            method: "nbs_customization.nbs_customization.nbs_customization.doctype.revenue_share_statement.revenue_share_statement.generate_revenue_share_statement",
            args: {
                contract_name: frm.doc.contract,
                period: frm.doc.period,
            },
            freeze: true,
            freeze_message: __("Generating revenue share statement..."),
            callback(r) {
                if (r.message) {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: __("Revenue Share Statement generated: {0}", [r.message]),
                        indicator: "green",
                    });
                }
            },
        });
    });
}
```

---

## Verification

- **Monthly Reconciliation**: manual "Generate for Period" button creates/refreshes the document. Penalty button appears only when `compliance_status == "Breach"`.
- **Revenue Share Statement**: manual "Generate for Period" button triggers auto-creation of Delivery Note and Sales Invoice.
