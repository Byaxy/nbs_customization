// Copyright (c) 2024, NBS Solutions and contributors
// For license information, please see license.txt

frappe.ui.form.on("Landed Cost Voucher", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.items && frm.doc.items.length > 0) {
			frm.add_custom_button(__("Distribution Calculator"), function () {
				open_distribution_dialog(frm);
			}).addClass("btn btn-danger btn-default btn-sm");
		}
	},
});

function nbs_format_value(value, df) {
	if (typeof frappe !== "undefined") {
		if (typeof frappe.format_value === "function") {
			return frappe.format_value(value, df);
		}
		if (typeof frappe.format === "function") {
			return frappe.format(value, df);
		}
		if (
			df &&
			df.fieldtype === "Currency" &&
			frappe.utils &&
			typeof frappe.utils.format_currency === "function"
		) {
			return frappe.utils.format_currency(value);
		}
	}
	return value;
}

function open_distribution_dialog(frm) {
	const total_charges = (frm.doc.taxes || []).reduce((sum, row) => sum + (row.amount || 0), 0);

	const dialog = new frappe.ui.Dialog({
		title: __("Landed Cost Distribution Calculator"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "info_html",
			},
			{
				fieldtype: "Select",
				fieldname: "distribution_basis",
				label: "Distribution Basis",
				options:
					"By Item Value (Amount)\nBy Quantity\nBy Weight\nManual (Equal Split)\nCustom Formula",
				default: "By Item Value (Amount)",
				reqd: 1,
			},
			{
				fieldtype: "Currency",
				fieldname: "total_charges_display",
				label: "Total Charges to Distribute",
				read_only: 1,
				default: total_charges,
			},
			{
				fieldtype: "Section Break",
				label: "Items",
			},
			{
				fieldtype: "HTML",
				fieldname: "items_table_html",
			},
		],
		primary_action_label: __("Apply Distribution"),
		primary_action(values) {
			apply_distribution(frm, dialog, values, total_charges);
			dialog.hide();
		},
	});

	dialog.fields_dict.info_html.$wrapper.html(`
        <div class="alert alert-info mb-3">
            <strong>How to use:</strong> 
		  <ul>
		  	<li>Select a distribution basis. The calculator will compute how much of the Total Charges to allocate to each item.</li>
		  	<li>Click Apply to update the LCV items table.</li>
		  	<li>You can then review each row before submitting.</li>
		  </ul>
        </div>
    `);

	build_items_preview(dialog, frm);

	dialog.fields_dict.distribution_basis.df.onchange = function () {
		build_items_preview(dialog, frm);
	};

	dialog.show();
}

function build_items_preview(dialog, frm) {
	const basis = dialog.get_value("distribution_basis");
	const items = frm.doc.items || [];
	const total_charges = (frm.doc.taxes || []).reduce((sum, row) => sum + (row.amount || 0), 0);

	// Calculate distribution weights
	let weights = [];
	let total_weight = 0;

	if (basis === "By Item Value (Amount)") {
		weights = items.map((r) => r.amount || 0);
		total_weight = weights.reduce((s, w) => s + w, 0);
	} else if (basis === "By Quantity") {
		weights = items.map((r) => r.qty || 0);
		total_weight = weights.reduce((s, w) => s + w, 0);
	} else if (basis === "By Weight") {
		weights = items.map((r) => r.net_weight || 0);
		total_weight = weights.reduce((s, w) => s + w, 0);
	} else if (basis === "Manual (Equal Split)") {
		weights = items.map(() => 1);
		total_weight = items.length;
	} else if (basis === "Custom Formula") {
		// Show input for custom weights per item
		build_custom_weight_table(dialog, frm, total_charges);
		return;
	}

	// Calculate allocation per item
	const allocations = weights.map((w, i) => {
		if (total_weight === 0) return 0;
		return (w / total_weight) * total_charges;
	});

	// Build preview table
	let rows = items
		.map(
			(item, i) => `
        <tr>
            <td>${item.item_code || "—"}</td>
            <td>${item.description || "—"}</td>
            <td class="text-right">${nbs_format_value(item.qty || 0, { fieldtype: "Float" })}</td>
            <td class="text-right">${nbs_format_value(item.amount || 0, { fieldtype: "Currency" })}</td>
            <td class="text-right">
                ${
					basis === "By Weight"
						? nbs_format_value(item.net_weight || 0, { fieldtype: "Float" })
						: "—"
				}
            </td>
            <td class="text-right font-weight-bold text-primary">
                ${nbs_format_value(allocations[i], { fieldtype: "Currency" })}
            </td>
        </tr>
    `,
		)
		.join("");

	dialog.fields_dict.items_table_html.$wrapper.html(`
        <div style="overflow-x: auto;">
            <table class="table table-bordered table-sm" style="font-size: 12px;">
                <thead class="thead-light">
                    <tr>
                        <th>${__("Item Code")}</th>
                        <th>${__("Description")}</th>
                        <th class="text-right">${__("Qty")}</th>
                        <th class="text-right">${__("Amount")}</th>
                        <th class="text-right">${__("Weight")}</th>
                        <th class="text-right">${__("Allocated Charge")}</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
                <tfoot>
                    <tr class="font-weight-bold">
                        <td colspan="5" class="text-right">${__("Total Allocated:")}</td>
                        <td class="text-right">
                            ${nbs_format_value(
								allocations.reduce((s, a) => s + a, 0),
								{ fieldtype: "Currency" },
							)}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
    `);

	// Store allocations for apply step
	dialog._allocations = allocations;
	dialog._basis = basis;
}

function build_custom_weight_table(dialog, frm, total_charges) {
	const items = frm.doc.items || [];

	let rows = items
		.map(
			(item, i) => `
        <tr>
            <td>${item.item_code || "—"}</td>
            <td>${item.description || "—"}</td>
            <td class="text-right">${nbs_format_value(item.amount || 0, { fieldtype: "Currency" })}</td>
            <td>
                <input type="number" class="form-control form-control-sm custom-weight"
                    data-index="${i}" value="0" min="0" step="0.01"
                    style="width: 100px; text-align: right;">
            </td>
            <td class="text-right allocated-amount font-weight-bold text-primary">—</td>
        </tr>
    `,
		)
		.join("");

	const html = `
        <div style="overflow-x: auto;">
            <p class="text-muted small">
                Enter a weight/value for each item. 
                The system will distribute charges proportionally.
            </p>
            <table class="table table-bordered table-sm" style="font-size: 12px;">
                <thead class="thead-light">
                    <tr>
                        <th>${__("Item Code")}</th>
                        <th>${__("Description")}</th>
                        <th class="text-right">${__("Item Amount")}</th>
                        <th>${__("Custom Weight")}</th>
                        <th class="text-right">${__("Allocated Charge")}</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;

	dialog.fields_dict.items_table_html.$wrapper.html(html);

	// Live recalculation as weights are entered
	dialog.fields_dict.items_table_html.$wrapper.on("input", ".custom-weight", function () {
		const weights = [];
		dialog.fields_dict.items_table_html.$wrapper.find(".custom-weight").each(function () {
			weights.push(parseFloat($(this).val()) || 0);
		});

		const total_w = weights.reduce((s, w) => s + w, 0);
		const allocations = weights.map((w) => (total_w > 0 ? (w / total_w) * total_charges : 0));

		dialog.fields_dict.items_table_html.$wrapper.find(".allocated-amount").each(function (i) {
			$(this).text(nbs_format_value(allocations[i], { fieldtype: "Currency" }));
		});

		dialog._allocations = allocations;
		dialog._basis = "Custom Formula";
	});

	dialog._allocations = items.map(() => 0);
	dialog._basis = "Custom Formula";
}

function apply_distribution(frm, dialog, values, total_charges) {
	const allocations = dialog._allocations;
	if (!allocations || !allocations.length) {
		frappe.msgprint(__("Please select a distribution basis first."));
		return;
	}

	const items = frm.doc.items || [];
	let applied = 0;

	items.forEach((item, i) => {
		const allocated = flt(allocations[i], 2);
		frappe.model.set_value(item.doctype, item.name, "applicable_charges", allocated);
		applied++;
	});

	frm.refresh_field("items");

	frappe.show_alert(
		{
			message: __(
				`Distribution applied to ${applied} items. ` +
					`Review the amounts in the Items table before submitting.`,
			),
			indicator: "green",
		},
		6,
	);
}
