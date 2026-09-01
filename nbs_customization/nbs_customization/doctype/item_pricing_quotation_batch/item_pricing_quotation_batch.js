// Copyright (c) 2026, Charles Byakutaga/NBS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item Pricing Quotation Batch", {
	refresh(frm) {
		if (frm.is_new()) frm.enable_save();
		_add_buttons(frm);
	},

	company(frm) {
		if (frm.doc.company) {
			frappe.db.get_value("Company", frm.doc.company, "default_currency").then((r) => {
				if (r.message) frm.set_value("company_currency", r.message.default_currency);
			});
		}
	},

	quote_currency(frm) {
		_fetch_fx(frm);
	},

	company_currency(frm) {
		_fetch_fx(frm);
	},

	exchange_rate_date(frm) {
		_fetch_fx(frm);
	},
});

frappe.ui.form.on("Item Pricing Quotation Batch Item", {
	qty(frm) {
		frm.set_value("total_base", "");
	},

	unit_cost(frm) {
		frm.set_value("total_base", "");
	},

	target_margin_pct(frm) {
		frm.set_value("total_final", "");
	},
});

function _fetch_fx(frm) {
	if (!frm.doc.quote_currency || !frm.doc.company_currency) return;
	if (frm.doc.quote_currency === frm.doc.company_currency) {
		frm.set_value("exchange_rate", 1);
		return;
	}
	// don't overwrite manual edit if user just typed
	frappe.call({
		method: "nbs_customization.utils.pricing.get_exchange_rate",
		args: {
			from_currency: frm.doc.quote_currency,
			to_currency: frm.doc.company_currency,
			date: frm.doc.exchange_rate_date || frm.doc.posting_date || frappe.datetime.get_today(),
		},
		callback(r) {
			if (r.message && flt(r.message)) {
				// only auto-fill if current is 0/1 or matches fetched? keep manual override if user edited
				if (!flt(frm.doc.exchange_rate) || flt(frm.doc.exchange_rate) === 1) {
					frm.set_value("exchange_rate", r.message);
				}
			}
		},
	});
}

function _add_buttons(frm) {
	if (frm.doc.docstatus !== 0) return;
	if (!frm.doc.items || !frm.doc.items.length) return;

	frm.add_custom_button(__("Recalculate Allocations"), () => {
		frm.save();
	}, __("Actions"));

	if (frm.doc.docstatus === 0 && frm.doc.items.length) {
		frm.add_custom_button(
			__("Preview Totals"),
			() => {
				let html = `<div style="max-height:420px;overflow:auto;"><table class="table table-bordered small" style="min-width:720px;"><thead><tr><th>Item</th><th>Qty</th><th>True Cost / Unit</th><th>Final / Unit</th><th>Final Total</th></tr></thead><tbody>`;
				for (const r of frm.doc.items) {
					html += `<tr><td>${r.item_code}</td><td class="text-right">${r.qty}</td><td class="text-right">${format_currency(r.true_cost_per_unit || 0)}</td><td class="text-right" style="font-weight:600">${format_currency(r.final_rate_per_unit || 0)}</td><td class="text-right">${format_currency(r.final_total || 0)}</td></tr>`;
				}
				html += `</tbody></table><div class="text-muted small">Totals — Base ${format_currency(frm.doc.total_base || 0)} · True Cost ${format_currency(frm.doc.total_true_cost || 0)} · Final ${format_currency(frm.doc.total_final || 0)} · Standard Selling source ${frm.doc.standard_selling_source_tier || "30%"} (FX ${frm.doc.exchange_rate || 1})</div></div>`;
				const preview = new frappe.ui.Dialog({
					title: __("Allocation Preview"),
					size: "extra-large",
					indicator: "blue",
				});
				preview.$body.html(html);
				preview.show();
			},
			__("Actions")
		);
	}
}
