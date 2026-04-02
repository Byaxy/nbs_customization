// Copyright (c) 2026, NBS Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Purchase Receipt", {
	setup(frm) {
		// Filter Inbound Shipments based on POs in the Items table
		frm.set_query("custom_inbound_shipment", () => {
			// Get unique POs from the items table
			const pr_pos = [
				...new Set((frm.doc.items || []).map((i) => i.purchase_order).filter(Boolean)),
			];

			if (!pr_pos.length) {
				return {
					filters: {
						docstatus: 1,
						company: frm.doc.company,
						name: ["in", ["__none__"]],
					},
				};
			}

			return {
				query: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_shipments_filtered_by_pos",
				filters: {
					pos: pr_pos,
					company: frm.doc.company,
				},
			};
		});
	},
	refresh(frm) {
		render_shipment_link_status(frm);
		add_shipment_link_button(frm);
	},
});

function render_shipment_link_status(frm) {
	// Show a clear info band when linked
	const $header = frm.fields_dict.custom_inbound_shipment
		? frm.get_field("custom_inbound_shipment").$wrapper
		: null;

	if ($header) $header.find(".shipment-link-info").remove();

	if (frm.doc.custom_inbound_shipment) {
		if ($header) {
			$header.append(`
                <div class="shipment-link-info alert alert-success mt-1 mb-0"
                    style="font-size:12px;">
                    ✔ Linked to Inbound Shipment
                    <a href="/app/inbound-shipment/${frm.doc.custom_inbound_shipment}"
                        target="_blank">
                        <b>${frm.doc.custom_inbound_shipment}</b>
                    </a>
                </div>
            `);
		}
	}
}

function add_shipment_link_button(frm) {
	frm.remove_custom_button(__("Link to Inbound Shipment"), __("Actions"));
	frm.remove_custom_button(__("Unlink from Inbound Shipment"), __("Actions"));

	if (frm.doc.docstatus !== 1) return;

	if (!frm.doc.custom_inbound_shipment) {
		// Show link button on unlinked submitted PRs
		frm.add_custom_button(
			__("Link to Inbound Shipment"),
			() => {
				open_link_dialog(frm);
			},
			__("Actions"),
		);
	}
}

function open_link_dialog(frm) {
	// Build the list of POs on this PR for pre-filtering shipments
	const pr_pos = [
		...new Set((frm.doc.items || []).map((i) => i.purchase_order).filter(Boolean)),
	];

	const dialog = new frappe.ui.Dialog({
		title: __("Link to Inbound Shipment"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "info_html",
			},
			{
				fieldtype: "Link",
				fieldname: "shipment",
				label: "Inbound Shipment",
				options: "Inbound Shipment",
				reqd: 1,
				get_query() {
					// Use the same advanced filtering logic as the main form field
					if (!pr_pos.length) {
						return {
							filters: {
								docstatus: 1,
								company: frm.doc.company,
								name: ["in", ["__none__"]],
							},
						};
					}

					return {
						query: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_shipments_filtered_by_pos",
						filters: {
							pos: pr_pos,
							company: frm.doc.company,
						},
					};
				},
			},
			{
				fieldtype: "HTML",
				fieldname: "validation_html",
			},
		],
		primary_action_label: __("Link"),
		primary_action(values) {
			if (!values.shipment) return;

			dialog.get_primary_btn().set_working();

			frappe.call({
				method: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.validate_and_link_pr_to_shipment",
				args: {
					pr_name: frm.doc.name,
					shipment_name: values.shipment,
				},
				callback(r) {
					dialog.get_primary_btn().done_working();
					if (!r.message) return;

					if (r.message.warnings && r.message.warnings.length) {
						// Show warnings but still succeed
						const warn_html = r.message.warnings.map((w) => `<li>${w}</li>`).join("");
						frappe.msgprint({
							title: __("Linked with Warnings"),
							message: `<ul>${warn_html}</ul>
                                <br>The Purchase Receipt has been linked.
                                Please review the discrepancies.`,
							indicator: "orange",
						});
					} else {
						frappe.show_alert(
							{
								message: __(
									`Purchase Receipt <b>${frm.doc.name}</b> linked to ` +
										`Inbound Shipment <b>${values.shipment}</b>.`,
								),
								indicator: "green",
							},
							6,
						);
					}

					dialog.hide();
					frm.reload_doc();
				},
				error: () => {
					dialog.get_primary_btn().done_working();
				},
			});
		},
	});

	// Info panel
	const po_text = pr_pos.length
		? `POs on this receipt: <b>${pr_pos.join(", ")}</b>`
		: `<span class="text-warning">⚠ No Purchase Orders found on items. Linking may fail validation.</span>`;

	dialog.fields_dict.info_html.$wrapper.html(`
        <div class="alert alert-info mb-2" style="font-size:12px;">
            ${po_text}<br>
            Only submitted shipments containing these POs will be valid targets.
        </div>
    `);

	// Live validation preview when shipment is selected
	dialog.fields_dict.shipment.df.onchange = function () {
		const shipment_name = dialog.get_value("shipment");
		const $preview = dialog.fields_dict.validation_html.$wrapper;

		$preview.html("");
		if (!shipment_name) return;

		$preview.html(`<p class="text-muted small">Checking compatibility...</p>`);

		frappe.call({
			method: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_shipment_summary",
			args: { shipment_name },
			callback(r) {
				if (!r.message) return;
				const s = r.message;
				$preview.html(`
                    <div class="alert alert-secondary mb-0 mt-1" style="font-size:12px;">
                        <b>${shipment_name}</b> — 
                        ${s.shipping_mode} | ${s.carrier} |
                        ${s.pr_count} PR(s) linked |
                        Status: <b>${s.status}</b>
                    </div>
                `);
			},
		});
	};

	dialog.show();
}
