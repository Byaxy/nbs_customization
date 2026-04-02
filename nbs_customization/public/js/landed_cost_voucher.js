// Copyright (c) 2024, NBS Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Landed Cost Voucher", {
	refresh(frm) {
		if (
			frm.doc.docstatus === 0 &&
			frm.doc.custom_linked_shipment &&
			frm.doc.items &&
			frm.doc.items.length > 0
		) {
			frm.add_custom_button(__("Distribution Calculator"), () => {
				open_distribution_dialog(frm);
			}).addClass("btn btn-danger btn-default btn-sm");
		}
	},
});

// ------------------------------------------------------------------ //
// Utility                                                              //
// ------------------------------------------------------------------ //

function nbs_format_value(value, df) {
	if (typeof frappe !== "undefined") {
		if (typeof frappe.format_value === "function") return frappe.format_value(value, df);
		if (typeof frappe.format === "function") return frappe.format(value, df);
	}
	return value;
}

// ------------------------------------------------------------------ //
// Dialog                                                               //
// ------------------------------------------------------------------ //

function open_distribution_dialog(frm) {
	const total_charges = (frm.doc.taxes || []).reduce((s, r) => s + (r.amount || 0), 0);
	const linked_shipment = frm.doc.custom_linked_shipment;
	const items = frm.doc.items || [];

	if (!linked_shipment) {
		frappe.msgprint({
			title: __("No Shipment Linked"),
			message: __(
				"This Landed Cost Voucher has no linked Inbound Shipment. " +
					"Weight-based distribution requires a shipment.",
			),
			indicator: "red",
		});
		return;
	}

	if (!items.length) {
		frappe.msgprint({
			title: __("No Items"),
			message: __(
				"Please click <b>Get Items</b> before running the Distribution Calculator.",
			),
			indicator: "orange",
		});
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Distribution Calculator — By Chargeable Weight"),
		size: "extra-large",
		fields: [
			{ fieldtype: "HTML", fieldname: "info_html" },
			{
				fieldtype: "Currency",
				fieldname: "total_charges_display",
				label: "Total Charges to Distribute",
				read_only: 1,
				default: total_charges,
			},
			{ fieldtype: "Section Break", label: "Item Chargeable Weight Allocation" },
			{ fieldtype: "HTML", fieldname: "items_table_html" },
		],
		primary_action_label: __("Apply Distribution"),
		primary_action() {
			apply_weight_distribution(frm, dialog);
			dialog.hide();
		},
	});

	dialog.fields_dict.info_html.$wrapper.html(`
		<div class="alert alert-info mb-2" style="font-size:12px;">
			<strong>Chargeable Weight Distribution:</strong>
			Each item receives a share of the total charges proportional to its
			<b>allocated chargeable weight</b> from Inbound Shipment
			<b>${linked_shipment}</b>.<br>
			After applying, ERPNext's distribution is locked to
			<b>Distribute Manually</b>.
		</div>
	`);

	// Show loading state in the table while fetching
	dialog.fields_dict.items_table_html.$wrapper.html(`
		<p class="text-muted p-3">
			<i class="fa fa-spinner fa-spin"></i> Fetching shipment weight data...
		</p>
	`);

	dialog.show();

	frappe.call({
		method: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_item_weights_from_shipment",
		args: { shipment_name: linked_shipment },
		callback(r) {
			if (!r.message || !Object.keys(r.message).length) {
				dialog.fields_dict.items_table_html.$wrapper.html(`
					<div class="alert alert-danger mb-0">
						Could not fetch weight data from shipment
						<b>${linked_shipment}</b>.
						Ensure the shipment has packages and package items with weights set.
					</div>
				`);
				dialog.get_primary_btn().prop("disabled", true);
				return;
			}

			frappe.call({
				method: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_item_net_weights_from_shipment",
				args: { shipment_name: linked_shipment },
				callback(nr) {
					const net_weight_map = nr && nr.message ? nr.message : {};
					build_weight_preview(dialog, frm, total_charges, r.message, net_weight_map);
				},
			});
		},
	});
}

// ------------------------------------------------------------------ //
// Preview table                                                        //
// ------------------------------------------------------------------ //
async function build_weight_preview(dialog, frm, total_charges, weight_map, net_weight_map) {
	const items = frm.doc.items || [];

	// 1. Map Purchase Receipt Items to their Parent Purchase Orders
	// We gather all unique PR Item names to fetch their 'purchase_order'
	const pr_item_names = items
		.filter((i) => i.purchase_receipt_item)
		.map((i) => i.purchase_receipt_item);

	let pr_to_po_map = {};

	if (pr_item_names.length > 0) {
		try {
			const result = await frappe.call({
				method: "nbs_customization.nbs_customization.doctype.inbound_shipment.inbound_shipment.get_pr_items_purchase_orders",
				args: { pr_item_names: pr_item_names },
			});
			if (result.message) {
				pr_to_po_map = result.message;
			}
		} catch (error) {
			console.error("Error fetching PR purchase orders:", error);
			frappe.msgprint(__("Could not fetch Purchase Order data for some items."));
		}
	}

	// 2. Build enriched items using the fetched PO data
	const enriched = items.map((item) => {
		const purchase_order = pr_to_po_map[item.purchase_receipt_item] || "";
		const key = `${purchase_order}||${item.item_code}`;
		const chargeable_wt = flt(weight_map[key] || 0, 3);
		const shipment_net_wt = flt((net_weight_map || {})[key] || 0, 3);

		return { item, chargeable_wt, shipment_net_wt };
	});

	const total_chargeable_wt = enriched.reduce((s, r) => s + r.chargeable_wt, 0);

	// Warn if any item has zero chargeable weight
	const missing = enriched.filter((r) => r.chargeable_wt <= 0);
	const warn_html = missing.length
		? `<div class="alert alert-warning mb-2" style="font-size:12px;">
			<strong>⚠ ${missing.length} item(s)</strong> have no chargeable weight
			from the shipment and will receive <b>zero</b> allocation:<br>
			${missing.map((r) => `<b>${r.item.item_code}</b>`).join(", ")}
		   </div>`
		: `<div class="alert alert-success mb-2" style="font-size:12px;">
			✔ All items have chargeable weight data.
		   </div>`;

	// Calculate monetary allocations
	const allocations = enriched.map(({ chargeable_wt }) => {
		if (total_chargeable_wt <= 0 || chargeable_wt <= 0) return 0;
		return (chargeable_wt / total_chargeable_wt) * total_charges;
	});

	const total_allocated = allocations.reduce((s, a) => s + a, 0);

	const rows_html = enriched
		.map(({ item, chargeable_wt, shipment_net_wt }, i) => {
			const wt_pct =
				total_chargeable_wt > 0
					? flt((chargeable_wt / total_chargeable_wt) * 100, 2) + "%"
					: "—";
			return `
			<tr>
				<td>${item.item_code || "—"}</td>
				<td>${item.description || "—"}</td>
				<td class="text-right">
					${nbs_format_value(item.qty || 0, { fieldtype: "Float" })}
				</td>
				<td class="text-right">
					${nbs_format_value(item.amount || 0, { fieldtype: "Currency" })}
				</td>
				<td class="text-right">
					${nbs_format_value(shipment_net_wt, { fieldtype: "Float" })}
				</td>
				<td class="text-right font-weight-bold">
					${nbs_format_value(chargeable_wt, { fieldtype: "Float" })}
				</td>
				<td class="text-right text-muted" style="font-size:11px;">${wt_pct}</td>
				<td class="text-right font-weight-bold text-primary">
					${nbs_format_value(allocations[i], { fieldtype: "Currency" })}
				</td>
			</tr>
		`;
		})
		.join("");

	dialog.fields_dict.items_table_html.$wrapper.html(`
		${warn_html}
		<div style="overflow-x: auto;">
			<table class="table table-bordered table-sm" style="font-size:12px;">
				<thead class="thead-light">
					<tr>
						<th>${__("Item Code")}</th>
						<th>${__("Description")}</th>
						<th class="text-right">${__("Qty")}</th>
						<th class="text-right">${__("Amount")}</th>
						<th class="text-right">${__("Net Wt (kg)")}</th>
						<th class="text-right">${__("Chargeable Wt (kg)")}</th>
						<th class="text-right">${__("Wt %")}</th>
						<th class="text-right">${__("Applicable Charge")}</th>
					</tr>
				</thead>
				<tbody>${rows_html}</tbody>
				<tfoot>
					<tr class="font-weight-bold">
						<td colspan="4" class="text-right">${__("Totals:")}</td>
						<td class="text-right">
							${nbs_format_value(
								enriched.reduce((s, r) => s + flt(r.shipment_net_wt), 0),
								{ fieldtype: "Float" },
							)}
						</td>
						<td class="text-right">
							${nbs_format_value(total_chargeable_wt, { fieldtype: "Float" })}
						</td>
						<td class="text-right">100%</td>
						<td class="text-right">
							${nbs_format_value(total_allocated, { fieldtype: "Currency" })}
						</td>
					</tr>
				</tfoot>
			</table>
		</div>
	`);

	// Store allocations for the apply step
	dialog._allocations = allocations;
	dialog._total_chargeable_wt = total_chargeable_wt;
}

// ------------------------------------------------------------------ //
// Apply                                                                //
// ------------------------------------------------------------------ //

function apply_weight_distribution(frm, dialog) {
	const allocations = dialog._allocations;

	if (!allocations || !allocations.length) {
		frappe.msgprint(__("No allocation data found. Please reopen the calculator."));
		return;
	}

	if (!dialog._total_chargeable_wt) {
		frappe.msgprint(__("Total chargeable weight is zero — cannot distribute."));
		return;
	}

	const items = frm.doc.items || [];
	let applied = 0;

	items.forEach((item, i) => {
		frappe.model.set_value(
			item.doctype,
			item.name,
			"applicable_charges",
			flt(allocations[i], 2),
		);
		applied++;
	});

	// Lock ERPNext's distribution so it never auto-overrides our values
	frm.set_value("distribute_charges_based_on", "Distribute Manually");
	frm.refresh_field("items");

	frappe.show_alert(
		{
			message: __(
				`Chargeable weight distribution applied to ${applied} item(s). ` +
					`Distribution locked to <b>Distribute Manually</b>. ` +
					`Review each row then submit.`,
			),
			indicator: "green",
		},
		8,
	);
}
