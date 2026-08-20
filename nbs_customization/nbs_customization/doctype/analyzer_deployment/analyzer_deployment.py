# Copyright (c) 2026, Charles Byakutaga/NBS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AnalyzerDeployment(Document):
    def validate(self):
        self._detect_status_transition()

    def _detect_status_transition(self):
        if self.is_new():
            return

        old = self.get_doc_before_save()
        if not old:
            return

        new_status = self.deployment_status
        old_status = old.deployment_status

        if new_status == old_status:
            return

        handlers = {
            "Deployed": self._on_deployed,
            "Under Service": self._on_under_service,
            "Temporarily Retrieved": self._on_retrieved,
            "Permanently Retrieved": self._on_permanently_retrieved,
        }

        handler = handlers.get(new_status)
        if handler:
            handler(old_status=old_status)

    def _on_deployed(self, old_status=None):
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_deployment_status",
            "Deployed",
        )
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_placement_contract",
            self.contract,
        )
        self._create_asset_movement(
            from_location=self.asset_storage_location,
            to_location=self.asset_location,
            purpose="Transfer",
        )

    def _on_under_service(self, old_status=None):
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_deployment_status",
            "Under Service",
        )

    def _on_retrieved(self, old_status=None):
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_deployment_status",
            "Warehouse",
        )

    def _on_permanently_retrieved(self, old_status=None):
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_deployment_status",
            "Warehouse",
        )
        frappe.db.set_value(
            "Asset",
            self.asset,
            "custom_current_placement_contract",
            None,
        )
        self._create_asset_movement(
            from_location=self.asset_location,
            to_location=self.asset_storage_location,
            purpose="Transfer",
        )

    def _create_asset_movement(self, from_location=None, to_location=None, purpose="Transfer"):
        if not frappe.db.exists("Asset", self.asset):
            return

        movement = frappe.get_doc({
            "doctype": "Asset Movement",
            "company": frappe.db.get_value("Asset", self.asset, "company"),
            "purpose": purpose,
            "transaction_date": self.deployment_date or frappe.utils.today(),
            "assets": [
                {
                    "asset": self.asset,
                    "source_location": from_location,
                    "target_location": to_location,
                }
            ],
        })
        movement.insert(ignore_permissions=True)
        movement.submit()
        return movement
