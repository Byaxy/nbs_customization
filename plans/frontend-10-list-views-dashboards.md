# F10 — List Views and Dashboards

**Depends on:** All prior tasks (backend + frontend)
**Provides:** Color-coded indicators and list view enhancements for placement DocTypes

---

## Objective

Add color-coded status indicators on list views and form dashboards for:
- `Instrument Placement Contract` — `contract_status`
- `Monthly Reconciliation` — `compliance_status`
- `Analyzer Deployment` — `deployment_status`
- `Repossession Request` — `status`
- `Ownership Transfer Request` — `status`

---

## Files to modify/create

| File | Action |
|------|--------|
| `nbs_customization/nbs_customization/nbs_customization/doctype/instrument_placement_contract/instrument_placement_contract_list.js` | Create — list view settings |
| `nbs_customization/nbs_customization/nbs_customization/doctype/monthly_reconciliation/monthly_reconciliation_list.js` | Create |
| `nbs_customization/nbs_customization/nbs_customization/doctype/analyzer_deployment/analyzer_deployment_list.js` | Create |
| `nbs_customization/nbs_customization/nbs_customization/doctype/repossession_request/repossession_request_list.js` | Create |
| `nbs_customization/nbs_customization/nbs_customization/doctype/ownership_transfer_request/ownership_transfer_request_list.js` | Create |

---

## 1. Status color maps

| DocType | Field | Map |
|---------|-------|-----|
| Instrument Placement Contract | `contract_status` | Draft=gray, Active=green, Fulfilled=blue, Breached=red, Terminated=orange, Expired=darkgray |
| Monthly Reconciliation | `compliance_status` | Compliant=green, Shortfall=orange, Grace Period=blue, Breach=red |
| Analyzer Deployment | `deployment_status` | Deployed=green, Under Service=orange, Temporarily Retrieved=blue, Permanently Retrieved=gray |
| Repossession Request | `status` | Draft=gray, Pending Approval=orange, Approved=blue, Analyzer Retrieved=green, Closed=darkgray |
| Ownership Transfer Request | `status` | Draft=gray, Pending Finance Review=orange, Pending Legal Review=orange, Approved=blue, Transfer Completed=green |

---

## 2. List view JavaScript — example pattern

Each file follows the same structure. Example for the Contract:

```javascript
// instrument_placement_contract_list.js

frappe.listview_settings["Instrument Placement Contract"] = {
    get_indicator(doc) {
        const status_map = {
            "Draft": [__("Draft"), "gray"],
            "Active": [__("Active"), "green"],
            "Fulfilled": [__("Fulfilled"), "blue"],
            "Breached": [__("Breached"), "red"],
            "Terminated": [__("Terminated"), "orange"],
            "Expired": [__("Expired"), "darkgray"],
        };
        return status_map[doc.contract_status] || [__("Unknown"), "gray"];
    },
};
```

### Monthly Reconciliation

```javascript
// monthly_reconciliation_list.js

frappe.listview_settings["Monthly Reconciliation"] = {
    get_indicator(doc) {
        const map = {
            "Compliant": [__("Compliant"), "green"],
            "Shortfall": [__("Shortfall"), "orange"],
            "Grace Period": [__("Grace Period"), "blue"],
            "Breach": [__("Breach"), "red"],
        };
        return map[doc.compliance_status] || [__("Unknown"), "gray"];
    },
};
```

### Analyzer Deployment

```javascript
// analyzer_deployment_list.js

frappe.listview_settings["Analyzer Deployment"] = {
    get_indicator(doc) {
        const map = {
            "Deployed": [__("Deployed"), "green"],
            "Under Service": [__("Under Service"), "orange"],
            "Temporarily Retrieved": [__("Temporarily Retrieved"), "blue"],
            "Permanently Retrieved": [__("Permanently Retrieved"), "gray"],
        };
        return map[doc.deployment_status] || [__("Unknown"), "gray"];
    },
};
```

### Repossession Request

```javascript
// repossession_request_list.js

frappe.listview_settings["Repossession Request"] = {
    get_indicator(doc) {
        const map = {
            "Draft": [__("Draft"), "gray"],
            "Pending Approval": [__("Pending Approval"), "orange"],
            "Approved": [__("Approved"), "blue"],
            "Analyzer Retrieved": [__("Analyzer Retrieved"), "green"],
            "Closed": [__("Closed"), "darkgray"],
        };
        return map[doc.status] || [__("Unknown"), "gray"];
    },
};
```

### Ownership Transfer Request

```javascript
// ownership_transfer_request_list.js

frappe.listview_settings["Ownership Transfer Request"] = {
    get_indicator(doc) {
        const map = {
            "Draft": [__("Draft"), "gray"],
            "Pending Finance Review": [__("Pending Finance Review"), "orange"],
            "Pending Legal Review": [__("Pending Legal Review"), "orange"],
            "Approved": [__("Approved"), "blue"],
            "Transfer Completed": [__("Transfer Completed"), "green"],
        };
        return map[doc.status] || [__("Unknown"), "gray"];
    },
};
```

---

## 3. Form dashboard indicators

Additionally, for the Contract form, add a `get_dashboard_data` hook for a richer recovery-progress view:

```python
# In instrument_placement_contract.py controller:

def get_dashboard_data(self):
    """Return chart data for the recovery progress dashboard."""
    return {
        "field": "recovery_pct_collected",
        "label": "Recovery Progress",
        "fieldtype": "Percent",
    }
```

---

## Verification

- List views show colored indicators matching the maps above.
- Indicators update in real-time as status changes.
- Contract form shows the recovery progress bar (already handled in F4's `_show_recovery_progress`).
