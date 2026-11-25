const NBS_UNIQUE_ITEM_DOCTYPES = {
	Quotation: "Quotation Item",
	"Sales Order": "Sales Order Item",
	"Purchase Order": "Purchase Order Item",
	"Request for Quotation": "Request for Quotation Item",
	"Loan Waybill": "Loan Waybill Item",
};

function nbs_duplicate_item_rows(frm) {
	const rows_by_item = new Map();

	(frm.doc.items || []).forEach((row) => {
		if (!row.item_code) return;
		const rows = rows_by_item.get(row.item_code) || [];
		rows.push(`#${row.idx}`);
		rows_by_item.set(row.item_code, rows);
	});

	return [...rows_by_item.entries()].filter(([, rows]) => rows.length > 1);
}

function nbs_show_duplicate_items(duplicates, block_save) {
	if (!duplicates.length) return false;

	const details = duplicates
		.map(
			([item_code, rows]) =>
				`<li><b>${frappe.utils.escape_html(item_code)}</b>: ${__("rows")} ${rows.join(
					", "
				)}</li>`
		)
		.join("");

	frappe.msgprint({
		title: __("Duplicate Items"),
		indicator: "red",
		message:
			__("Each item must appear on only one row. Combine the quantities for:") +
			`<ul>${details}</ul>`,
	});

	if (block_save) frappe.validated = false;
	return true;
}

Object.entries(NBS_UNIQUE_ITEM_DOCTYPES).forEach(([parent, child]) => {
	frappe.ui.form.on(parent, {
		before_save(frm) {
			nbs_show_duplicate_items(nbs_duplicate_item_rows(frm), true);
		},
	});

	frappe.ui.form.on(child, {
		item_code(frm) {
			nbs_show_duplicate_items(nbs_duplicate_item_rows(frm), false);
		},
	});
});
