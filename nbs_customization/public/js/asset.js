frappe.ui.form.on("Asset", {
	refresh(frm) {
		const contract = frm.doc.custom_current_placement_contract;
		if (!contract) return;

		frm.dashboard.add_comment(
			__("Placed under {0} — status {1}", [
				contract,
				frm.doc.custom_current_deployment_status || __("Unknown"),
			]),
			"blue",
			true
		);

		frappe.db
			.get_value("Instrument Placement Contract", contract, "contract_status")
			.then((r) => {
				if (r.message && r.message.contract_status === "Active") {
					frm.set_df_property("custom_serial_no", "read_only", 1);
					frm.set_df_property("custom_instrument_specification", "read_only", 1);
				}
			});
	},
});
